"""
Unit tests for Phase 1 core models.

Verifies DocumentChunk, ChunkPayload, UploadResponse, and DocumentListResponse
can be constructed and serialised correctly.
"""

from datetime import UTC, datetime

from app.core.models import (
    ChunkPayload,
    DocumentChunk,
    DocumentListResponse,
    DocumentRecord,
    DocumentStatus,
    UploadResponse,
)


class TestDocumentChunk:
    def test_construction(self):
        chunk = DocumentChunk(
            chunk_id="00000000-0000-0000-0000-000000000001",
            document_id="doc-123",
            filename="manual.pdf",
            text="Replace the oil filter every 500 hours.",
            page_number=3,
            chunk_index=0,
            char_count=38,
        )
        assert chunk.chunk_id == "00000000-0000-0000-0000-000000000001"
        assert chunk.page_number == 3
        assert chunk.chunk_index == 0
        assert chunk.char_count == 38

    def test_serialisation(self):
        chunk = DocumentChunk(
            chunk_id="abc",
            document_id="doc",
            filename="f.pdf",
            text="hello",
            page_number=1,
            chunk_index=0,
            char_count=5,
        )
        data = chunk.model_dump()
        assert data["chunk_id"] == "abc"
        assert data["text"] == "hello"


class TestChunkPayload:
    def test_construction(self):
        payload = ChunkPayload(
            chunk_id="abc",
            document_id="doc",
            filename="manual.pdf",
            page_number=1,
            chunk_index=0,
            text="Torque the bolts to 80 Nm.",
        )
        assert payload.document_id == "doc"
        assert payload.page_number == 1

    def test_model_dump_is_json_compatible(self):
        payload = ChunkPayload(
            chunk_id="abc",
            document_id="doc",
            filename="f.pdf",
            page_number=2,
            chunk_index=1,
            text="text",
        )
        data = payload.model_dump()
        # All values must be JSON primitives for Qdrant payload storage
        for value in data.values():
            assert isinstance(value, (str, int, float, bool, type(None)))


class TestUploadResponse:
    def test_construction(self):
        resp = UploadResponse(
            document_id="abc-123",
            filename="manual.pdf",
            status=DocumentStatus.PENDING,
            message="File accepted. Ingestion running in background.",
        )
        assert resp.document_id == "abc-123"
        assert resp.status == DocumentStatus.PENDING

    def test_status_is_always_pending(self):
        resp = UploadResponse(
            document_id="x",
            filename="x.pdf",
            status=DocumentStatus.PENDING,
            message="ok",
        )
        assert resp.status == "PENDING"


class TestDocumentListResponse:
    def test_empty_list(self):
        resp = DocumentListResponse(documents=[], total=0)
        assert resp.total == 0
        assert resp.documents == []

    def test_with_records(self):
        record = DocumentRecord(
            document_id="abc",
            filename="f.pdf",
            file_hash="sha256:abc",
            status=DocumentStatus.READY,
            chunk_count=5,
            upload_timestamp=datetime.now(UTC),
            file_size_bytes=1024,
        )
        resp = DocumentListResponse(documents=[record], total=1)
        assert resp.total == 1
        assert resp.documents[0].document_id == "abc"
