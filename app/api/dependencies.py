"""
FastAPI dependency providers.

All injectable dependencies are defined here and imported by routers.
Using Depends() rather than direct imports enables:
  - Easy test overrides via app.dependency_overrides
  - Clean separation between wiring and logic
  - Singleton lifecycle management via lifespan context

Dependencies are added per phase:

  Phase 0: get_settings
  Phase 1: get_document_repository, get_qdrant_repository, get_ingestion_service
  Phase 2: get_query_service
  Phase 3: get_rag_graph

Usage in a router:
    from typing import Annotated
    from fastapi import Depends
    from app.api.dependencies import get_ingestion_service
    from app.services.ingestion_service import IngestionService

    @router.post("/upload")
    async def upload(service: Annotated[IngestionService, Depends(get_ingestion_service)]):
        ...
"""

from typing import Annotated

from fastapi import Depends, Request

from app.core.config import Settings, get_settings

# Re-export for convenient import in routers
SettingsDep = Annotated[Settings, Depends(get_settings)]


# ── Phase 1 ───────────────────────────────────────────────────────────────────


def get_document_repository(settings: Settings = Depends(get_settings)):
    """
    Return a DocumentRepository backed by the configured SQLite database.

    The db_path is derived from the upload_dir setting so that all data
    for a deployment lives under the same directory.
    """
    import os

    from app.db.document_repository import DocumentRepository

    db_path = os.path.join(settings.upload_dir, "documents.db")
    return DocumentRepository(db_path=db_path)


def get_qdrant_repository(settings: Settings = Depends(get_settings)):
    """
    Return a QdrantRepository connected to the configured Qdrant instance.

    The QdrantClient is constructed fresh per request. For production
    workloads, this should be replaced with a shared client stored in
    app.state (attached during lifespan) to avoid per-request TCP overhead.
    """
    from app.db.qdrant_client import get_qdrant_client
    from app.db.qdrant_repository import QdrantRepository

    client = get_qdrant_client(settings)
    return QdrantRepository(
        client=client,
        collection_name=settings.qdrant_collection_name,
        vector_size=settings.embedding_dimensions,
    )


def get_ingestion_service(
    settings: Settings = Depends(get_settings),
    doc_repo=Depends(get_document_repository),
    qdrant_repo=Depends(get_qdrant_repository),
):
    """
    Return an IngestionService wired with its dependencies.

    The service holds an asyncio.Semaphore for concurrency control.
    Each request gets a new IngestionService instance — the semaphore
    is per-instance, which is fine since ingestion is a fire-and-forget
    background task and the service is lightweight.
    """
    from app.services.ingestion_service import IngestionService

    return IngestionService(
        settings=settings,
        doc_repo=doc_repo,
        qdrant_repo=qdrant_repo,
    )


# ── Phase 2 / 3 ───────────────────────────────────────────────────────────────


def get_query_service(request: Request):
    """
    Return a QueryService backed by the compiled LangGraph RAG graph.

    The graph is compiled once during startup (FastAPI lifespan) and stored
    on app.state.rag_graph. Streaming deps (embedder, qdrant_repo, llm config)
    are also stored on app.state so stream_query() can bypass the graph.

    In tests, this dependency is overridden via:
        client.app.dependency_overrides[get_query_service] = lambda: mock_svc
    so app.state is never accessed in unit tests.
    """
    from app.services.query_service import QueryService

    state = request.app.state
    return QueryService(
        graph=state.rag_graph,
        embedder=getattr(state, "embedder", None),
        qdrant_repo=getattr(state, "qdrant_repo", None),
        ollama_base_url=getattr(state, "ollama_base_url", "http://localhost:11434"),
        llm_model=getattr(state, "llm_model", "llama3.2:3b"),
        max_context_chars=getattr(state, "max_context_chars", 8000),
    )
