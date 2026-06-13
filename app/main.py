"""
FastAPI application factory.

Entry point for the Industrial RAG Platform HTTP API.

Structure:
  create_app()    — builds and configures the FastAPI instance
  lifespan()      — handles startup and shutdown side effects
  app             — module-level instance used by uvicorn

Startup sequence (managed by lifespan):
  1. Configure logging
  2. Log startup event
  3. Phase 1+: initialise Qdrant collection
  4. Phase 3+: compile LangGraph RAG graph

To run locally (outside Docker):
    uvicorn app.main:app --reload --port 8000
"""

import os
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.routers import chat, documents, system
from app.core.config import get_settings
from app.core.exceptions import AppError
from app.core.logging import configure_logging, get_logger

logger = get_logger(__name__)


# ── Lifespan ──────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Manage application startup and shutdown.

    Resources that should be initialised once and shared across all requests
    (database clients, compiled graphs) are created here and attached to
    app.state so they can be accessed via request.app.state in dependencies.

    Startup tasks added per phase:
      Phase 0: configure logging
      Phase 1: initialise Qdrant collection, create SQLite tables
      Phase 3: compile and store LangGraph RAG graph
    """
    # Resolve settings via DI overrides so tests can inject test settings.
    # app.dependency_overrides[get_settings] is set in conftest.py for tests.
    settings_factory = app.dependency_overrides.get(get_settings, get_settings)
    settings = settings_factory()
    configure_logging(settings)

    logger.info(
        "Starting Industrial RAG Platform",
        extra={
            "env": settings.app_env,
            "llm_model": settings.llm_model,
            "embedding_model": settings.embedding_model,
            "qdrant_collection": settings.qdrant_collection_name,
        },
    )

    # ── Phase 1: ensure upload directory exists ───────────────────────────────
    os.makedirs(settings.upload_dir, exist_ok=True)

    # ── Phase 1: SQLite document registry setup ───────────────────────────────
    from app.db.document_repository import DocumentRepository

    db_path = os.path.join(settings.upload_dir, "documents.db")
    doc_repo = DocumentRepository(db_path=db_path)
    doc_repo.create_tables()

    # ── Phase 1 + 3: Qdrant, embedder, LLM client, and RAG graph ─────────────
    # Only attempt live service connections when not in test mode.
    # Unit tests override get_query_service entirely and never touch app.state.
    if settings.app_env != "test":
        import ollama

        from app.agents.rag_graph import build_rag_graph
        from app.db.qdrant_client import get_qdrant_client
        from app.db.qdrant_repository import QdrantRepository
        from app.rag.embedder import OllamaEmbedder
        from app.rag.sparse_embedder import SparseEmbedder

        qdrant_client = get_qdrant_client(settings)
        qdrant_repo = QdrantRepository(
            client=qdrant_client,
            collection_name=settings.qdrant_collection_name,
            vector_size=settings.embedding_dimensions,
        )
        qdrant_repo.ensure_collection_exists()
        logger.info(
            "Qdrant collection ready",
            extra={"collection": settings.qdrant_collection_name},
        )

        embedder = OllamaEmbedder(
            base_url=settings.ollama_base_url,
            model=settings.embedding_model,
        )
        # SparseEmbedder uses lazy initialization — the BM25 model is downloaded
        # on first embed call, not at startup, to keep startup time fast.
        sparse_embedder = SparseEmbedder(model_name=settings.sparse_embedding_model)
        llm_client = ollama.Client(host=settings.ollama_base_url)

        app.state.rag_graph = build_rag_graph(
            embedder=embedder,
            qdrant_repo=qdrant_repo,
            llm_client=llm_client,
            settings=settings,
            sparse_embedder=sparse_embedder,
        )
        # Store deps so QueryService and IngestionService can access them.
        app.state.embedder = embedder
        app.state.sparse_embedder = sparse_embedder
        app.state.qdrant_repo = qdrant_repo
        app.state.ollama_base_url = settings.ollama_base_url
        app.state.llm_model = settings.llm_model
        app.state.max_context_chars = settings.max_context_chars

        logger.info(
            "RAG graph compiled",
            extra={
                "llm_model": settings.llm_model,
                "embedding_model": settings.embedding_model,
                "sparse_embedding_model": settings.sparse_embedding_model,
                "max_context_chars": settings.max_context_chars,
            },
        )

    yield  # Application is running; handle requests

    logger.info("Shutting down Industrial RAG Platform")


# ── Application Factory ───────────────────────────────────────────────────────


def create_app() -> FastAPI:
    """
    Build and configure the FastAPI application.

    Separated from the module-level `app` variable so the factory can be
    called in tests with different settings without affecting the global state.
    """
    settings = get_settings()

    app = FastAPI(
        title="Industrial Document Intelligence Platform",
        description=(
            "Semantic search and retrieval-augmented generation over "
            "industrial technical documents. Upload PDFs, ask questions, "
            "receive grounded answers with source citations."
        ),
        version="0.1.0",
        lifespan=lifespan,
        # OpenAPI / Swagger UI
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # ── Middleware ────────────────────────────────────────────────────────────

    # CORS — permissive for local development; restrict origins in production.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if not settings.is_production else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    # Request ID — generate or propagate a correlation ID for every request.
    # The ID is available as request.state.request_id in all handlers and
    # is echoed back in the X-Request-ID response header.
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    # ── Exception Handlers ────────────────────────────────────────────────────

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        """
        Convert AppError subclasses into a consistent JSON error response.

        All domain errors (DocumentNotFoundError, FileTooLargeError, etc.)
        inherit from AppError and are handled here. Unhandled exceptions
        fall through to FastAPI's default 500 handler.
        """
        request_id = getattr(request.state, "request_id", None)

        logger.warning(
            "Application error",
            extra={
                "error_code": exc.code,
                "error_message": exc.message,
                "status_code": exc.status_code,
                "request_id": request_id,
                "path": request.url.path,
            },
        )

        return JSONResponse(
            status_code=exc.status_code,
            content={
                "detail": {
                    "code": exc.code,
                    "message": exc.message,
                    "request_id": request_id,
                }
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        """Catch-all for unexpected exceptions — log and return 500."""
        request_id = getattr(request.state, "request_id", None)

        logger.error(
            "Unhandled exception",
            extra={"request_id": request_id, "path": request.url.path},
            exc_info=exc,
        )

        return JSONResponse(
            status_code=500,
            content={
                "detail": {
                    "code": "INTERNAL_ERROR",
                    "message": "An unexpected error occurred. Please try again.",
                    "request_id": request_id,
                }
            },
        )

    # ── Routers ───────────────────────────────────────────────────────────────

    app.include_router(system.router, prefix="/v1")
    app.include_router(documents.router, prefix="/v1")
    app.include_router(chat.router, prefix="/v1")

    return app


# ── Module-level instance (used by uvicorn) ───────────────────────────────────

app = create_app()
