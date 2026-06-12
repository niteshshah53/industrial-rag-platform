"""
Semantic retrieval from the Qdrant vector store.

The Retriever is the RAG layer component responsible for:
  1. Embedding the question using OllamaEmbedder
  2. Searching Qdrant for the closest chunk vectors
  3. Applying score threshold and optional document filter

Design decisions:
  - The Retriever is a thin coordinator between OllamaEmbedder and
    QdrantRepository. It does not contain search logic itself — that
    lives in QdrantRepository.search().
  - Synchronous — callers (QueryService) run this in run_in_executor.
  - Accepts both embedder and repository as constructor arguments so
    unit tests can inject mocks without touching the Ollama or Qdrant clients.

Usage:
    retriever = Retriever(embedder=embedder, qdrant_repo=qdrant_repo)
    chunks = retriever.retrieve(
        question="What is the max operating temperature?",
        top_k=5,
        score_threshold=0.6,
        document_id_filter=None,
    )
"""

from app.core.logging import get_logger
from app.core.models import RetrievedChunk
from app.db.qdrant_repository import QdrantRepository
from app.rag.embedder import OllamaEmbedder

logger = get_logger(__name__)


class Retriever:
    """
    Embeds a question and retrieves the most relevant chunks from Qdrant.

    Args:
        embedder: OllamaEmbedder instance for question embedding.
        qdrant_repo: QdrantRepository instance for vector search.
    """

    def __init__(self, embedder: OllamaEmbedder, qdrant_repo: QdrantRepository) -> None:
        self._embedder = embedder
        self._qdrant_repo = qdrant_repo

    def retrieve(
        self,
        question: str,
        top_k: int,
        score_threshold: float,
        document_id_filter: str | None = None,
    ) -> list[RetrievedChunk]:
        """
        Embed the question and return chunks above the score threshold.

        Args:
            question: Natural-language question to embed and search.
            top_k: Maximum number of chunks to return.
            score_threshold: Minimum cosine similarity [0, 1].
            document_id_filter: If set, restrict search to this document.

        Returns:
            List of RetrievedChunk objects sorted by score descending.
            Empty list when no chunks meet the threshold.

        Raises:
            ServiceUnavailableError: If Ollama or Qdrant are unreachable.
        """
        question_vector = self._embedder.embed_query(question)

        chunks = self._qdrant_repo.search(
            vector=question_vector,
            top_k=top_k,
            score_threshold=score_threshold,
            document_id_filter=document_id_filter,
        )

        logger.debug(
            "Retrieval complete",
            extra={
                "question_length": len(question),
                "top_k": top_k,
                "score_threshold": score_threshold,
                "retrieved_count": len(chunks),
                "top_score": chunks[0].score if chunks else None,
            },
        )

        return chunks
