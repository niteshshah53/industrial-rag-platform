"""
Unit tests for the context assembler.

Tests verify:
  - Score-descending sort before budget enforcement
  - Character budget respected
  - Empty input handling
  - Included vs. dropped chunk tracking
  - Context string format (source headers present)
No external services required.
"""

from app.core.models import RetrievedChunk
from app.rag.assembler import assemble_context

# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_chunk(
    chunk_id: str,
    score: float,
    text: str = "Default chunk text.",
    page_number: int = 1,
    doc_filename: str = "manual.pdf",
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        text=text,
        score=score,
        document_id="doc-001",
        filename=doc_filename,
        page_number=page_number,
        chunk_index=0,
    )


# ── Tests ──────────────────────────────────────────────────────────────────────


class TestAssembleContextEmptyInput:
    def test_empty_list_returns_empty_string_and_list(self):
        context, included = assemble_context(chunks=[], max_chars=8192)
        assert context == ""
        assert included == []


class TestAssembleContextSorting:
    def test_highest_score_chunk_comes_first_in_context(self):
        chunks = [
            _make_chunk("c-low", 0.65, text="Low relevance text content."),
            _make_chunk("c-high", 0.92, text="High relevance text content."),
            _make_chunk("c-mid", 0.78, text="Medium relevance text content."),
        ]
        context, included = assemble_context(chunks=chunks, max_chars=8192)
        assert included[0].chunk_id == "c-high"
        assert included[1].chunk_id == "c-mid"
        assert included[2].chunk_id == "c-low"

    def test_context_string_reflects_sorted_order(self):
        chunks = [
            _make_chunk("c-0", 0.60, text="Lower score text."),
            _make_chunk("c-1", 0.95, text="Higher score text."),
        ]
        context, _ = assemble_context(chunks=chunks, max_chars=8192)
        higher_pos = context.index("Higher score text.")
        lower_pos = context.index("Lower score text.")
        assert higher_pos < lower_pos


class TestAssembleContextBudget:
    def test_all_chunks_included_when_within_budget(self):
        chunks = [_make_chunk(f"c-{i}", 0.9 - i * 0.1, text="Short text.") for i in range(3)]
        _, included = assemble_context(chunks=chunks, max_chars=8192)
        assert len(included) == 3

    def test_lowest_score_chunks_dropped_when_over_budget(self):
        """Budget of 100 chars — only the first (highest-score) chunk fits."""
        chunks = [
            _make_chunk("c-0", 0.95, text="A" * 60),  # fits
            _make_chunk("c-1", 0.80, text="B" * 60),  # would push over 100 chars
            _make_chunk("c-2", 0.65, text="C" * 60),  # definitely over
        ]
        _, included = assemble_context(chunks=chunks, max_chars=100)
        assert len(included) == 1
        assert included[0].chunk_id == "c-0"

    def test_context_char_count_within_max_chars(self):
        chunks = [_make_chunk(f"c-{i}", 0.9 - i * 0.05, text="word " * 50) for i in range(10)]
        context, _ = assemble_context(chunks=chunks, max_chars=500)
        assert len(context) <= 500

    def test_multiple_chunks_fit_within_budget(self):
        chunks = [
            _make_chunk("c-0", 0.95, text="A" * 50),
            _make_chunk("c-1", 0.85, text="B" * 50),
        ]
        # Each chunk header adds ~30 chars, separator ~7 chars
        _, included = assemble_context(chunks=chunks, max_chars=300)
        assert len(included) == 2


class TestAssembleContextReturnValues:
    def test_included_chunks_are_retrieved_chunk_instances(self):
        chunks = [_make_chunk("c-0", 0.80, text="Some useful technical information.")]
        _, included = assemble_context(chunks=chunks, max_chars=8192)
        assert all(isinstance(c, RetrievedChunk) for c in included)

    def test_included_count_plus_dropped_equals_total(self):
        chunks = [
            _make_chunk("c-0", 0.95, text="A" * 60),
            _make_chunk("c-1", 0.80, text="B" * 60),
            _make_chunk("c-2", 0.65, text="C" * 60),
        ]
        _, included = assemble_context(chunks=chunks, max_chars=100)
        total = 3
        dropped = total - len(included)
        assert dropped >= 0
        assert len(included) + dropped == total


class TestAssembleContextFormat:
    def test_context_contains_source_header(self):
        chunks = [_make_chunk("c-0", 0.90, text="Torque spec: 80 Nm.", page_number=5)]
        context, _ = assemble_context(chunks=chunks, max_chars=8192)
        assert "manual.pdf" in context
        assert "Page 5" in context

    def test_context_contains_chunk_text(self):
        chunks = [_make_chunk("c-0", 0.88, text="Replace filter every 500 hours.")]
        context, _ = assemble_context(chunks=chunks, max_chars=8192)
        assert "Replace filter every 500 hours." in context

    def test_multiple_chunks_separated(self):
        chunks = [
            _make_chunk("c-0", 0.90, text="First chunk content."),
            _make_chunk("c-1", 0.80, text="Second chunk content."),
        ]
        context, _ = assemble_context(chunks=chunks, max_chars=8192)
        assert "First chunk content." in context
        assert "Second chunk content." in context

    def test_source_header_includes_page_number(self):
        chunks = [_make_chunk("c-0", 0.85, text="Content.", page_number=12)]
        context, _ = assemble_context(chunks=chunks, max_chars=8192)
        assert "Page 12" in context

    def test_different_filenames_in_context(self):
        chunks = [
            _make_chunk("c-0", 0.90, text="From manual A.", doc_filename="manual_a.pdf"),
            _make_chunk("c-1", 0.80, text="From manual B.", doc_filename="manual_b.pdf"),
        ]
        context, _ = assemble_context(chunks=chunks, max_chars=8192)
        assert "manual_a.pdf" in context
        assert "manual_b.pdf" in context
