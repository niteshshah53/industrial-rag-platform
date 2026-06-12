"""
Retrieve node — embed the question and search Qdrant.

Responsibility: take `question`, `top_k`, `score_threshold`, and optional
`document_id` from state, embed the question via Ollama, search Qdrant,
and return `retrieved_chunks` (possibly empty).

Empty retrieval is NOT an error — the graph's conditional edge after this
node routes to END (returning a "no relevant documents" response) when the
chunk list is empty. The generate node is never called in that case.

Node signature (LangGraph convention):
    retrieve(state: RAGState) -> dict

Returns only the fields this node sets: {"retrieved_chunks": list[RetrievedChunk]}.
"""

from collections.abc import Callable

from app.agents.state import RAGState
from app.core.logging import get_logger
from app.db.qdrant_repository import QdrantRepository
from app.rag.embedder import OllamaEmbedder
from app.rag.retriever import Retriever

logger = get_logger(__name__)


def build_retrieve_node(
    embedder: OllamaEmbedder,
    qdrant_repo: QdrantRepository,
) -> Callable[[RAGState], dict]:
    """
    Build the retrieve node function with injected dependencies.

    Constructing the Retriever inside the factory (rather than accepting a
    Retriever directly) keeps the factory signature at the dependency level,
    which is consistent with how the graph builder assembles the pipeline.
    Tests inject mock embedder and qdrant_repo objects.

    Args:
        embedder: OllamaEmbedder for question embedding.
        qdrant_repo: QdrantRepository for vector search.

    Returns:
        LangGraph node function: (state: RAGState) -> dict.
    """
    retriever = Retriever(embedder=embedder, qdrant_repo=qdrant_repo)

    def retrieve(state: RAGState) -> dict:
        request_id = state.get("request_id", "")
        question = state["question"]

        logger.info(
            "Retrieve node: starting",
            extra={
                "request_id": request_id,
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
