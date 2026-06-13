"""
Sparse text embedder using BM25 via fastembed.

Produces sparse vector representations for hybrid search in Qdrant.
BM25 captures exact keyword matches (model names, part numbers, error codes)
that dense vectors can miss — particularly valuable for industrial documents.

The fastembed model is downloaded on first use and cached locally.
Subsequent calls are fast (pure Python tokenization + TF-IDF weighting).
"""

from functools import cached_property

from qdrant_client.models import SparseVector

from app.core.logging import get_logger

logger = get_logger(__name__)


class SparseEmbedder:
    """
    Generates BM25 sparse vectors via fastembed.SparseTextEmbedding.

    Args:
        model_name: fastembed sparse model identifier. Default is "Qdrant/bm25".
    """

    def __init__(self, model_name: str = "Qdrant/bm25") -> None:
        self._model_name = model_name

    @cached_property
    def _model(self):
        from fastembed import SparseTextEmbedding

        logger.info("Loading BM25 sparse embedding model", extra={"model": self._model_name})
        return SparseTextEmbedding(model_name=self._model_name)

    def embed_texts(self, texts: list[str]) -> list[SparseVector]:
        """
        Embed a batch of texts into sparse BM25 vectors.

        Args:
            texts: List of text strings to embed.

        Returns:
            List of SparseVector objects with indices and float32 weights.
        """
        results = list(self._model.embed(texts, batch_size=32))
        return [
            SparseVector(indices=e.indices.tolist(), values=e.values.tolist())
            for e in results
        ]

    def embed_query(self, text: str) -> SparseVector:
        """Embed a single query string into a sparse BM25 vector."""
        return self.embed_texts([text])[0]
