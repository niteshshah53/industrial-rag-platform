"""
Text embedding via the Ollama Python client.

Responsibilities:
  - Embed a list of DocumentChunk objects in configurable batches
  - Return (chunk, vector) pairs ready for Qdrant upsert
  - Raise ServiceUnavailableError if Ollama is unreachable

Design decisions:
  - Batched requests: Ollama processes one text at a time in its Python SDK,
    so we iterate the batch and collect results. The batch_size setting limits
    memory use and allows progress logging on large documents.
  - Synchronous Ollama client: the ollama library is sync-only. Callers
    must invoke this in run_in_executor (which IngestionService does).
  - No retry logic here — transient failures surface to IngestionService,
    which marks the document FAILED and logs the error. Retries belong at
    a higher orchestration level.

Usage:
    embedder = OllamaEmbedder(base_url="http://localhost:11434",
                              model="nomic-embed-text",
                              batch_size=32)
    pairs = embedder.embed(chunks)
    # pairs: list of (DocumentChunk, list[float])
"""

import ollama

from app.core.exceptions import ServiceUnavailableError
from app.core.logging import get_logger
from app.core.models import DocumentChunk

logger = get_logger(__name__)


class OllamaEmbedder:
    """
    Embeds DocumentChunk objects using a locally running Ollama model.

    Args:
        base_url: Base URL of the Ollama HTTP server.
        model: Name of the embedding model (e.g. "nomic-embed-text").
        batch_size: Number of chunks to embed per batch for progress logging.
    """

    def __init__(self, base_url: str, model: str, batch_size: int = 32) -> None:
        self._model = model
        self._batch_size = batch_size
        # The ollama library uses the OLLAMA_HOST env var or accepts a host kwarg.
        self._client = ollama.Client(host=base_url)

    def embed(self, chunks: list[DocumentChunk]) -> list[tuple[DocumentChunk, list[float]]]:
        """
        Embed a list of chunks, returning (chunk, vector) pairs.

        Args:
            chunks: DocumentChunk objects to embed.

        Returns:
            List of (DocumentChunk, embedding_vector) pairs in input order.

        Raises:
            ServiceUnavailableError: If Ollama cannot be reached.
        """
        if not chunks:
            return []

        results: list[tuple[DocumentChunk, list[float]]] = []
        total = len(chunks)

        for batch_start in range(0, total, self._batch_size):
            batch = chunks[batch_start : batch_start + self._batch_size]
            batch_end = min(batch_start + self._batch_size, total)

            logger.debug(
                "Embedding batch",
                extra={
                    "model": self._model,
                    "batch_start": batch_start,
                    "batch_end": batch_end,
                    "total": total,
                },
            )

            for chunk in batch:
                vector = self._embed_one(chunk.text)
                results.append((chunk, vector))

        logger.debug(
            "Embedding complete",
            extra={"model": self._model, "chunk_count": total},
        )

        return results

    def embed_query(self, text: str) -> list[float]:
        """
        Embed a single query string (e.g. a user question).

        This is a thin public wrapper around _embed_one for use by the
        retrieval path. Unlike embed(), it does not batch — a query is always
        a single text.

        Args:
            text: The question or search string to embed.

        Returns:
            Embedding vector as a list of floats.

        Raises:
            ServiceUnavailableError: If the Ollama server is unreachable.
        """
        return self._embed_one(text)

    def _embed_one(self, text: str) -> list[float]:
        """
        Embed a single text string.

        Raises:
            ServiceUnavailableError: If the Ollama server is unreachable.
        """
        try:
            response = self._client.embeddings(model=self._model, prompt=text)
            return response["embedding"]
        except Exception as exc:
            error_str = str(exc).lower()
            if any(kw in error_str for kw in ("connection", "refused", "timeout", "unreachable")):
                raise ServiceUnavailableError("ollama", detail=str(exc)) from exc
            # Re-raise unexpected errors so IngestionService can mark the doc FAILED.
            raise
