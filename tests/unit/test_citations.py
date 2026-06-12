"""
Unit tests for citation building.

Tests the _build_citations helper in query_service.py.
Verifies citation structure, ordering, and score rounding.
No external services required.
"""

from app.core.models import Citation, RetrievedChunk
from app.services.query_service import _build_citations

# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_chunk(
    chunk_id: str = "c-0",
    score: float = 0.85,
    filename: str = "manual.pdf",
    page_number: int = 1,
    chunk_index: int = 0,
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        text="Some retrieved text.",
        score=score,
        document_id="doc-001",
        filename=filename,
        page_number=page_number,
        chunk_index=chunk_index,
    )


# ── Tests ──────────────────────────────────────────────────────────────────────


class TestBuildCitationsEmptyInput:
    def test_empty_chunks_returns_empty_list(self):
        citations = _build_citations([])
        assert citations == []


class TestBuildCitationsStructure:
    def test_returns_citation_objects(self):
        chunks = [_make_chunk()]
        citations = _build_citations(chunks)
        assert all(isinstance(c, Citation) for c in citations)

    def test_one_citation_per_chunk(self):
        chunks = [_make_chunk(f"c-{i}") for i in range(4)]
        citations = _build_citations(chunks)
        assert len(citations) == 4

    def test_document_name_matches_filename(self):
        chunks = [_make_chunk(filename="hydraulic_manual.pdf")]
        citations = _build_citations(chunks)
        assert citations[0].document_name == "hydraulic_manual.pdf"

    def test_page_number_matches_chunk(self):
        chunks = [_make_chunk(page_number=7)]
        citations = _build_citations(chunks)
        assert citations[0].page_number == 7

    def test_chunk_index_matches_chunk(self):
        chunks = [_make_chunk(chunk_index=15)]
        citations = _build_citations(chunks)
        assert citations[0].chunk_index == 15

    def test_relevance_score_matches_chunk_score(self):
        chunks = [_make_chunk(score=0.834567)]
        citations = _build_citations(chunks)
        assert citations[0].relevance_score == round(0.834567, 4)

    def test_score_is_rounded_to_4_decimal_places(self):
        chunks = [_make_chunk(score=0.8345678901)]
        citations = _build_citations(chunks)
        assert citations[0].relevance_score == 0.8346


class TestBuildCitationsOrdering:
    def test_citation_order_matches_chunk_order(self):
        """Citations preserve the order of included_chunks (already sorted desc by assembler)."""
        chunks = [
            _make_chunk("c-0", score=0.95, page_number=1),
            _make_chunk("c-1", score=0.82, page_number=3),
            _make_chunk("c-2", score=0.71, page_number=7),
        ]
        citations = _build_citations(chunks)
        assert citations[0].page_number == 1
        assert citations[1].page_number == 3
        assert citations[2].page_number == 7

    def test_citations_scores_descending_when_input_is_sorted(self):
        chunks = [
            _make_chunk("c-0", score=0.95),
            _make_chunk("c-1", score=0.80),
            _make_chunk("c-2", score=0.65),
        ]
        citations = _build_citations(chunks)
        scores = [c.relevance_score for c in citations]
        assert scores == sorted(scores, reverse=True)


class TestBuildCitationsMultipleDocuments:
    def test_citations_from_different_documents(self):
        chunks = [
            _make_chunk("c-0", filename="doc_a.pdf", page_number=2),
            _make_chunk("c-1", filename="doc_b.pdf", page_number=5),
        ]
        citations = _build_citations(chunks)
        doc_names = {c.document_name for c in citations}
        assert doc_names == {"doc_a.pdf", "doc_b.pdf"}
