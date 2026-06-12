"""
FastAPI dependency providers.

All injectable dependencies are defined here and imported by routers.
Using Depends() rather than direct imports enables:
  - Easy test overrides via app.dependency_overrides
  - Clean separation between wiring and logic
  - Singleton lifecycle management via lifespan context

Dependencies are added per phase:

  Phase 0: get_settings
  Phase 1: get_qdrant_client, get_document_repository, get_ingestion_service
  Phase 2: get_query_service
  Phase 3: get_rag_graph

Usage in a router:
    from typing import Annotated
    from fastapi import Depends
    from app.api.dependencies import get_settings
    from app.core.config import Settings

    @router.get("/example")
    async def example(settings: Annotated[Settings, Depends(get_settings)]):
        ...
"""

from typing import Annotated

from fastapi import Depends

from app.core.config import Settings, get_settings

# Re-export for convenient import in routers
SettingsDep = Annotated[Settings, Depends(get_settings)]


# ── Phase 1 (added during Phase 1 implementation) ─────────────────────────────
#
# def get_qdrant_client() -> QdrantClient:
#     """Return the shared Qdrant client singleton."""
#     ...
#
# def get_document_repository(
#     client: Annotated[QdrantClient, Depends(get_qdrant_client)]
# ) -> DocumentRepository:
#     ...
#
# def get_ingestion_service(...) -> IngestionService:
#     ...


# ── Phase 2 (added during Phase 2 implementation) ─────────────────────────────
#
# def get_query_service(...) -> QueryService:
#     ...


# ── Phase 3 (added during Phase 3 implementation) ─────────────────────────────
#
# def get_rag_graph(request: Request) -> CompiledStateGraph:
#     """Return the compiled LangGraph RAG graph from application state."""
#     return request.app.state.rag_graph
