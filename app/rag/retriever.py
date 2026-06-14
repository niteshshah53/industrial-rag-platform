"""
Semantic retrieval from the Qdrant vector store.

Supports two search modes:
  - "dense":  cosine vector similarity only (original behavior)
  - "hybrid": BM25 sparse + dense, fused via Qdrant RRF (default)

When search_mode="hybrid" and a SparseEmbedder is available, the question is
embedded with both OllamaEmbedder (dense) and SparseEmbedder (BM25). Qdrant
fuses both result sets using Reciprocal Rank Fusion, improving recall for
queries containing exact keywords (part numbers, error codes, model names).

Falls back to dense-only search when SparseEmbedder is not provided or when
the caller explicitly sets search_mode="dense".
"""

from typing import TYPE_CHECKING

from app.core.logging import get_logger
from app.core.models import RetrievedChunk
from app.db.qdrant_repository import QdrantRepository
from app.rag.embedder import OllamaEmbedder

if TYPE_CHECKING:
    from app.rag.sparse_embedder import SparseEmbedder

logger = get_logger(__name__)


class Retriever:
    """
    Embeds a question and retrieves the most relevant chunks from Qdrant.

    Args:
        embedder: OllamaEmbedder instance for dense question embedding.
        qdrant_repo: QdrantRepository instance for vector search.
        sparse_embedder: Optional SparseEmbedder for BM25 hybrid search.
    """

    def __init__(
        self,
        embedder: OllamaEmbedder,
        qdrant_repo: QdrantRepository,
        sparse_embedder: "SparseEmbedder | None" = None,
    ) -> None:
        self._embedder = embedder
        self._qdrant_repo = qdrant_repo
        self._sparse_embedder = sparse_embedder

    def retrieve(
        self,
        question: str,
        top_k: int,
        score_threshold: float,
        document_id_filter: str | list[str] | None = None,
        search_mode: str = "hybrid",
    ) -> list[RetrievedChunk]:
        """
        Embed the question and return chunks above the score threshold.

        Args:
            question: Natural-language question to embed and search.
            top_k: Maximum number of chunks to return.
            score_threshold: Minimum cosine similarity [0, 1].
            document_id_filter: If set, restrict search to this document.
            search_mode: "hybrid" (BM25 + dense RRF) or "dense" (cosine only).

        Returns:
            List of RetrievedChunk objects sorted by score descending.
            Empty list when no chunks meet the threshold.

        Raises:
            ServiceUnavailableError: If Ollama or Qdrant are unreachable.
        """
        dense_vector = self._embedder.embed_query(question)

        use_hybrid = search_mode == "hybrid" and self._sparse_embedder is not None

        if use_hybrid:
            sparse_vector = self._sparse_embedder.embed_query(question)  # type: ignore[union-attr]
            chunks = self._qdrant_repo.hybrid_search(
                dense_vector=dense_vector,
                sparse_vector=sparse_vector,
                top_k=top_k,
                score_threshold=score_threshold,
                document_id_filter=document_id_filter,
            )
        else:
            chunks = self._qdrant_repo.search(
                vector=dense_vector,
                top_k=top_k,
                score_threshold=score_threshold,
                document_id_filter=document_id_filter,
            )

        logger.debug(
            "Retrieval complete",
            extra={
                "search_mode": "hybrid" if use_hybrid else "dense",
                "question_length": len(question),
                "top_k": top_k,
                "score_threshold": score_threshold,
                "retrieved_count": len(chunks),
                "top_score": chunks[0].score if chunks else None,
            },
        )

        return chunks
