"""
Unit tests for OllamaEmbedder.

All Ollama calls are mocked — no live Ollama instance required.
Tests verify batching logic, error mapping, and output shape.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.core.exceptions import ServiceUnavailableError
from app.core.models import DocumentChunk
from app.rag.embedder import OllamaEmbedder

# ── Fixtures ───────────────────────────────────────────────────────────────────


def _make_chunk(chunk_index: int = 0, text: str = "Sample text for embedding.") -> DocumentChunk:
    return DocumentChunk(
        chunk_id=f"chunk-{chunk_index:04d}",
        document_id="doc-123",
        filename="manual.pdf",
        text=text,
        page_number=1,
        chunk_index=chunk_index,
        char_count=len(text),
    )


def _make_embedder(batch_size: int = 4) -> OllamaEmbedder:
    return OllamaEmbedder(
        base_url="http://localhost:11434",
        model="nomic-embed-text",
        batch_size=batch_size,
    )


# ── Tests ──────────────────────────────────────────────────────────────────────


class TestOllamaEmbedderEmptyInput:
    def test_empty_list_returns_empty(self):
        embedder = _make_embedder()
        result = embedder.embed([])
        assert result == []


class TestOllamaEmbedderNormalPath:
    def test_returns_chunk_vector_pairs(self):
        fake_vector = [0.1] * 768
        chunks = [_make_chunk(0), _make_chunk(1)]

        with patch.object(OllamaEmbedder, "_embed_one", return_value=fake_vector):
            embedder = _make_embedder()
            pairs = embedder.embed(chunks)

        assert len(pairs) == 2
        for chunk, vector in pairs:
            assert isinstance(chunk, DocumentChunk)
            assert vector == fake_vector

    def test_output_order_matches_input_order(self):
        vectors = [[float(i)] * 768 for i in range(5)]
        chunks = [_make_chunk(i) for i in range(5)]
        call_count = 0

        def fake_embed(text: str) -> list[float]:
            nonlocal call_count
            result = vectors[call_count]
            call_count += 1
            return result

        with patch.object(OllamaEmbedder, "_embed_one", side_effect=fake_embed):
            embedder = _make_embedder()
            pairs = embedder.embed(chunks)

        for i, (chunk, vector) in enumerate(pairs):
            assert chunk.chunk_index == i
            assert vector == vectors[i]

    def test_chunk_objects_preserved_in_output(self):
        fake_vector = [0.0] * 768
        chunk = _make_chunk(0, text="Unique text for this test.")

        with patch.object(OllamaEmbedder, "_embed_one", return_value=fake_vector):
            embedder = _make_embedder()
            pairs = embedder.embed([chunk])

        returned_chunk, _ = pairs[0]
        assert returned_chunk is chunk


class TestOllamaEmbedderBatching:
    def test_all_chunks_embedded_across_batches(self):
        """With batch_size=3 and 7 chunks, all 7 must be embedded."""
        fake_vector = [0.5] * 768
        chunks = [_make_chunk(i) for i in range(7)]

        with patch.object(OllamaEmbedder, "_embed_one", return_value=fake_vector):
            embedder = _make_embedder(batch_size=3)
            pairs = embedder.embed(chunks)

        assert len(pairs) == 7

    def test_single_item_batch(self):
        fake_vector = [1.0] * 768
        chunks = [_make_chunk(0)]

        with patch.object(OllamaEmbedder, "_embed_one", return_value=fake_vector):
            embedder = _make_embedder(batch_size=1)
            pairs = embedder.embed(chunks)

        assert len(pairs) == 1


class TestOllamaEmbedderErrorHandling:
    def test_connection_refused_string_raises_service_unavailable(self):
        """Ollama raises generic exceptions with 'connection' in the message."""
        chunks = [_make_chunk(0)]

        mock_client = MagicMock()
        mock_client.embeddings.side_effect = Exception("Connection refused to localhost:11434")

        with patch("app.rag.embedder.ollama.Client", return_value=mock_client):
            embedder = _make_embedder()
            with pytest.raises(ServiceUnavailableError) as exc_info:
                embedder.embed(chunks)

        assert exc_info.value.service == "ollama"

    def test_timeout_error_raises_service_unavailable(self):
        """Timeout errors should map to ServiceUnavailableError."""
        chunks = [_make_chunk(0)]

        mock_client = MagicMock()
        mock_client.embeddings.side_effect = Exception("timeout waiting for response")

        with patch("app.rag.embedder.ollama.Client", return_value=mock_client):
            embedder = _make_embedder()
            with pytest.raises(ServiceUnavailableError):
                embedder.embed(chunks)

    def test_unexpected_error_propagates(self):
        """Non-connection errors should propagate for the caller to handle."""
        chunks = [_make_chunk(0)]

        mock_client = MagicMock()
        mock_client.embeddings.side_effect = ValueError("Model not found")

        with patch("app.rag.embedder.ollama.Client", return_value=mock_client):
            embedder = _make_embedder()
            with pytest.raises(ValueError, match="Model not found"):
                embedder.embed(chunks)
