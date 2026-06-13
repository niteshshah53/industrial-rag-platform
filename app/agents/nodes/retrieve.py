"""
Retrieve node — embed the question and search Qdrant.

Responsibility: take `question`, `top_k`, `score_threshold`, `search_mode`, and
optional `document_id` from state, embed the question, search Qdrant (dense or
hybrid depending on search_mode), and return `retrieved_chunks` (possibly empty).

Empty retrieval is NOT an error — the graph's conditional edge after this
node routes to END when the chunk list is empty.
"""

from collections.abc import Callable
from typing import TYPE_CHECKING

from app.agents.state import RAGState
from app.core.logging import get_logger
from app.db.qdrant_repository import QdrantRepository
from app.rag.embedder import OllamaEmbedder
from app.rag.retriever import Retriever

if TYPE_CHECKING:
    from app.rag.sparse_embedder import SparseEmbedder

logger = get_logger(__name__)


def build_retrieve_node(
    embedder: OllamaEmbedder,
    qdrant_repo: QdrantRepository,
    sparse_embedder: "SparseEmbedder | None" = None,
) -> Callable[[RAGState], dict]:
    """
    Build the retrieve node function with injected dependencies.

    Args:
        embedder: OllamaEmbedder for dense question embedding.
        qdrant_repo: QdrantRepository for vector search.
        sparse_embedder: Optional SparseEmbedder for BM25 hybrid search.

    Returns:
        LangGraph node function: (state: RAGState) -> dict.
    """
    retriever = Retriever(
        embedder=embedder,
        qdrant_repo=qdrant_repo,
        sparse_embedder=sparse_embedder,
    )

    def retrieve(state: RAGState) -> dict:
        request_id = state.get("request_id", "")
        question = state["question"]
        search_mode = state.get("search_mode", "hybrid")

        logger.info(
            "Retrieve node: starting",
            extra={
                "request_id": request_id,
                "search_mode": search_mode,
                "top_k": state.get("top_k"),
                "score_threshold": state.get("score_threshold"),
                "document_id_filter": state.get("document_id"),
            },
        )

        chunks = retriever.retrieve(
            question=question,
            top_k=state["top_k"],
            score_threshold=state["score_threshold"],
            document_id_filter=state.get("document_id"),
            search_mode=search_mode,
        )

        logger.info(
            "Retrieve node: complete",
            extra={
                "request_id": request_id,
                "retrieved_count": len(chunks),
                "top_score": chunks[0].score if chunks else None,
            },
        )

        return {"retrieved_chunks": chunks}

    return retrieve
