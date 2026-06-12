"""
Unit tests for the Retriever.

All Qdrant and Ollama calls are mocked. Tests verify:
  - threshold filtering behaviour
  - document_id filter forwarding
  - score-sorted output order
  - empty result handling
No Docker required.
"""

from unittest.mock import MagicMock

from app.core.models import RetrievedChunk
from app.rag.retriever import Retriever

# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_chunk(chunk_id: str, score: float, document_id: str = "doc-001") -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        text=f"Text for chunk {chunk_id}.",
        score=score,
        document_id=document_id,
        filename="manual.pdf",
        page_number=1,
        chunk_index=int(chunk_id.split("-")[-1]) if "-" in chunk_id else 0,
    )


def _make_retriever(
    embed_vector: list[float] | None = None,
    search_results: list[RetrievedChunk] | None = None,
) -> tuple[Retriever, MagicMock, MagicMock]:
    """Return (retriever, mock_embedder, mock_qdrant_repo)."""
    fake_vector = embed_vector or [0.1] * 768

    mock_embedder = MagicMock()
    mock_embedder.embed_query.return_value = fake_vector

    mock_qdrant = MagicMock()
    mock_qdrant.search.return_value = search_results or []

    retriever = Retriever(embedder=mock_embedder, qdrant_repo=mock_qdrant)
    return retriever, mock_embedder, mock_qdrant


# ── Tests ──────────────────────────────────────────────────────────────────────


class TestRetrieverCallsEmbedder:
    def test_embeds_question_before_search(self):
        retriever, mock_embedder, _ = _make_retriever()
        retriever.retrieve("What is the max temperature?", top_k=5, score_threshold=0.6)
        mock_embedder.embed_query.assert_called_once_with("What is the max temperature?")

    def test_passes_embedding_vector_to_qdrant(self):
        fake_vector = [0.42] * 768
        retriever, _, mock_qdrant = _make_retriever(embed_vector=fake_vector)
        retriever.retrieve("Question", top_k=3, score_threshold=0.5)
        call_args = mock_qdrant.search.call_args
        assert call_args.kwargs["vector"] == fake_vector


class TestRetrieverForwardsParameters:
    def test_forwards_top_k(self):
        retriever, _, mock_qdrant = _make_retriever()
        retriever.retrieve("Q", top_k=7, score_threshold=0.5)
        assert mock_qdrant.search.call_args.kwargs["top_k"] == 7

    def test_forwards_score_threshold(self):
        retriever, _, mock_qdrant = _make_retriever()
        retriever.retrieve("Q", top_k=5, score_threshold=0.75)
        assert mock_qdrant.search.call_args.kwargs["score_threshold"] == 0.75

    def test_forwards_document_id_filter_when_set(self):
        retriever, _, mock_qdrant = _make_retriever()
        retriever.retrieve("Q", top_k=5, score_threshold=0.6, document_id_filter="doc-abc")
        assert mock_qdrant.search.call_args.kwargs["document_id_filter"] == "doc-abc"

    def test_forwards_none_document_id_filter(self):
        retriever, _, mock_qdrant = _make_retriever()
        retriever.retrieve("Q", top_k=5, score_threshold=0.6, document_id_filter=None)
        assert mock_qdrant.search.call_args.kwargs["document_id_filter"] is None


class TestRetrieverResults:
    def test_returns_chunks_from_qdrant(self):
        chunks = [_make_chunk("c-0", 0.9), _make_chunk("c-1", 0.7)]
        retriever, _, _ = _make_retriever(search_results=chunks)
        result = retriever.retrieve("Q", top_k=5, score_threshold=0.6)
        assert len(result) == 2

    def test_returns_retrieved_chunk_objects(self):
        chunks = [_make_chunk("c-0", 0.85)]
        retriever, _, _ = _make_retriever(search_results=chunks)
        result = retriever.retrieve("Q", top_k=5, score_threshold=0.6)
        assert isinstance(result[0], RetrievedChunk)

    def test_empty_result_on_no_matching_chunks(self):
        retriever, _, _ = _make_retriever(search_results=[])
        result = retriever.retrieve("Q", top_k=5, score_threshold=0.99)
        assert result == []

    def test_preserves_output_order_from_qdrant(self):
        """Retriever does not reorder — Qdrant already returns sorted by score desc."""
        chunks = [
            _make_chunk("c-0", 0.92),
            _make_chunk("c-1", 0.77),
            _make_chunk("c-2", 0.61),
        ]
        retriever, _, _ = _make_retriever(search_results=chunks)
        result = retriever.retrieve("Q", top_k=5, score_threshold=0.6)
        scores = [r.score for r in result]
        assert scores == [0.92, 0.77, 0.61]


class TestRetrieverDocumentFilter:
    def test_with_document_filter_restricts_search(self):
        chunk = _make_chunk("c-0", 0.88, document_id="doc-xyz")
        retriever, _, mock_qdrant = _make_retriever(search_results=[chunk])
        result = retriever.retrieve("Q", top_k=5, score_threshold=0.6, document_id_filter="doc-xyz")
        assert len(result) == 1
        assert result[0].document_id == "doc-xyz"
        assert mock_qdrant.search.call_args.kwargs["document_id_filter"] == "doc-xyz"
