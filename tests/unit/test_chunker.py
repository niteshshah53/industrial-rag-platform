"""
Unit tests for DocumentChunker.

Verifies chunking logic, chunk ID determinism, page number attribution,
and edge cases (empty pages, very short text, long text).
No external services required.
"""

import hashlib
import uuid

from app.core.models import DocumentChunk
from app.rag.chunker import DocumentChunker, _make_chunk_id


class TestMakeChunkId:
    def test_returns_valid_uuid_string(self):
        chunk_id = _make_chunk_id("doc-123", 0)
        # Should parse as UUID without error
        parsed = uuid.UUID(chunk_id)
        assert str(parsed) == chunk_id

    def test_deterministic(self):
        id1 = _make_chunk_id("doc-abc", 5)
        id2 = _make_chunk_id("doc-abc", 5)
        assert id1 == id2

    def test_different_index_gives_different_id(self):
        id0 = _make_chunk_id("doc-abc", 0)
        id1 = _make_chunk_id("doc-abc", 1)
        assert id0 != id1

    def test_different_document_gives_different_id(self):
        id_a = _make_chunk_id("doc-aaa", 0)
        id_b = _make_chunk_id("doc-bbb", 0)
        assert id_a != id_b

    def test_matches_expected_algorithm(self):
        """Verify the algorithm is sha256(f'{doc_id}:{idx}')[:32] as UUID hex."""
        doc_id, idx = "test-doc", 7
        digest = hashlib.sha256(f"{doc_id}:{idx}".encode()).hexdigest()
        expected = str(uuid.UUID(hex=digest[:32]))
        assert _make_chunk_id(doc_id, idx) == expected


class TestDocumentChunkerBasic:
    def setup_method(self):
        self.chunker = DocumentChunker(chunk_size_chars=200, chunk_overlap_chars=20)

    def test_returns_list_of_document_chunks(self):
        pages = [(1, "A" * 100)]
        chunks = self.chunker.chunk(pages, "doc-1", "file.pdf")
        assert isinstance(chunks, list)
        for chunk in chunks:
            assert isinstance(chunk, DocumentChunk)

    def test_empty_pages_returns_empty_list(self):
        chunks = self.chunker.chunk([], "doc-1", "file.pdf")
        assert chunks == []

    def test_blank_page_text_is_skipped(self):
        pages = [(1, "   \n\n   ")]
        chunks = self.chunker.chunk(pages, "doc-1", "file.pdf")
        assert chunks == []

    def test_chunk_index_is_global_and_zero_indexed(self):
        long_text = "word " * 200  # 1000 chars → multiple chunks at size 200
        pages = [(1, long_text)]
        chunks = self.chunker.chunk(pages, "doc-1", "file.pdf")
        indices = [c.chunk_index for c in chunks]
        assert indices[0] == 0
        assert indices == list(range(len(chunks)))

    def test_document_id_and_filename_propagated(self):
        pages = [(1, "Some text content for testing.")]
        chunks = self.chunker.chunk(pages, "my-doc-id", "my_file.pdf")
        for chunk in chunks:
            assert chunk.document_id == "my-doc-id"
            assert chunk.filename == "my_file.pdf"

    def test_char_count_matches_text_length(self):
        pages = [(1, "Hello world! This is a test sentence for chunking.")]
        chunks = self.chunker.chunk(pages, "doc-1", "f.pdf")
        for chunk in chunks:
            assert chunk.char_count == len(chunk.text)


class TestDocumentChunkerPageNumbers:
    def setup_method(self):
        self.chunker = DocumentChunker(chunk_size_chars=100, chunk_overlap_chars=10)

    def test_page_number_attributed_correctly(self):
        pages = [
            (1, "Page one content that is fairly short."),
            (2, "Page two content that is also fairly short."),
        ]
        chunks = self.chunker.chunk(pages, "doc-1", "f.pdf")
        page_1_chunks = [c for c in chunks if c.page_number == 1]
        page_2_chunks = [c for c in chunks if c.page_number == 2]
        assert len(page_1_chunks) >= 1
        assert len(page_2_chunks) >= 1

    def test_chunks_do_not_span_pages(self):
        """Each chunk should come from exactly one page."""
        pages = [
            (3, "Third page with content about maintenance procedures."),
            (5, "Fifth page with content about safety regulations."),
        ]
        chunks = self.chunker.chunk(pages, "doc-1", "f.pdf")
        for chunk in chunks:
            assert chunk.page_number in (3, 5)

    def test_chunk_index_is_global_across_pages(self):
        """chunk_index must be globally monotonic, not reset per page."""
        pages = [
            (1, "First page content for testing global chunk index."),
            (2, "Second page content for testing global chunk index."),
        ]
        chunks = self.chunker.chunk(pages, "doc-1", "f.pdf")
        indices = [c.chunk_index for c in chunks]
        assert indices == sorted(indices)
        assert len(set(indices)) == len(indices)  # no duplicates


class TestDocumentChunkerChunkIds:
    def test_chunk_ids_are_unique(self):
        chunker = DocumentChunker(chunk_size_chars=100, chunk_overlap_chars=10)
        long_text = "word " * 200
        pages = [(1, long_text)]
        chunks = chunker.chunk(pages, "doc-1", "f.pdf")
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids))

    def test_chunk_ids_are_deterministic(self):
        chunker = DocumentChunker(chunk_size_chars=100, chunk_overlap_chars=10)
        pages = [(1, "Deterministic chunking test content for validation.")]
        chunks1 = chunker.chunk(pages, "doc-abc", "f.pdf")
        chunks2 = chunker.chunk(pages, "doc-abc", "f.pdf")
        assert [c.chunk_id for c in chunks1] == [c.chunk_id for c in chunks2]

    def test_same_text_different_document_gives_different_ids(self):
        chunker = DocumentChunker(chunk_size_chars=200, chunk_overlap_chars=20)
        pages = [(1, "Shared text content.")]
        chunks_a = chunker.chunk(pages, "doc-aaa", "f.pdf")
        chunks_b = chunker.chunk(pages, "doc-bbb", "f.pdf")
        assert chunks_a[0].chunk_id != chunks_b[0].chunk_id


class TestDocumentChunkerLongText:
    def test_long_text_produces_multiple_chunks(self):
        chunker = DocumentChunker(chunk_size_chars=100, chunk_overlap_chars=10)
        long_text = "The quick brown fox jumps over the lazy dog. " * 50  # 2250 chars
        pages = [(1, long_text)]
        chunks = chunker.chunk(pages, "doc-1", "f.pdf")
        assert len(chunks) > 1

    def test_all_chunks_within_size_limit(self):
        chunk_size = 150
        chunker = DocumentChunker(chunk_size_chars=chunk_size, chunk_overlap_chars=15)
        long_text = "word " * 500
        pages = [(1, long_text)]
        chunks = chunker.chunk(pages, "doc-1", "f.pdf")
        for chunk in chunks:
            # Allow small tolerance for separator handling by LangChain splitter
            assert chunk.char_count <= chunk_size + 20
