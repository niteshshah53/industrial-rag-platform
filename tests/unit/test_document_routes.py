"""
Unit tests for the document management API routes.

All service layer calls are mocked. No database or vector store required.
Tests focus on HTTP concerns: status codes, request parsing, response shape.
"""

from datetime import UTC, datetime
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.core.exceptions import (
    DocumentAlreadyExistsError,
    DocumentNotFoundError,
    FileTooLargeError,
    InvalidFileTypeError,
)
from app.core.models import (
    DocumentListResponse,
    DocumentRecord,
    DocumentStatus,
    UploadResponse,
)

# ── Helpers ────────────────────────────────────────────────────────────────────

_PDF_MAGIC = b"%PDF-1.4\n"


def _make_record(
    document_id: str = "doc-001",
    filename: str = "manual.pdf",
    status: DocumentStatus = DocumentStatus.READY,
) -> DocumentRecord:
    return DocumentRecord(
        document_id=document_id,
        filename=filename,
        file_hash="sha256:abc",
        status=status,
        chunk_count=10,
        upload_timestamp=datetime.now(UTC),
        file_size_bytes=1024,
    )


def _mock_service():
    """Return a MagicMock that looks like an IngestionService."""
    svc = MagicMock()
    svc.upload = AsyncMock()
    svc.run_ingestion = AsyncMock()
    svc.list_documents = MagicMock()
    svc.get_document = MagicMock()
    svc.delete_document = AsyncMock()
    return svc


# ── Upload tests ───────────────────────────────────────────────────────────────


class TestUploadEndpoint:
    def test_returns_202_on_success(self, client: TestClient):
        mock_svc = _mock_service()
        mock_svc.upload.return_value = UploadResponse(
            document_id="doc-001",
            filename="manual.pdf",
            status=DocumentStatus.PENDING,
            message="File accepted. Ingestion running in background.",
        )

        from app.api.dependencies import get_ingestion_service

        client.app.dependency_overrides[get_ingestion_service] = lambda: mock_svc
        try:
            response = client.post(
                "/v1/documents/upload",
                files={
                    "file": ("manual.pdf", BytesIO(_PDF_MAGIC + b"fake content"), "application/pdf")
                },
            )
        finally:
            del client.app.dependency_overrides[get_ingestion_service]

        assert response.status_code == 202

    def test_response_contains_document_id(self, client: TestClient):
        mock_svc = _mock_service()
        mock_svc.upload.return_value = UploadResponse(
            document_id="abc-123",
            filename="manual.pdf",
            status=DocumentStatus.PENDING,
            message="File accepted. Ingestion running in background.",
        )

        from app.api.dependencies import get_ingestion_service

        client.app.dependency_overrides[get_ingestion_service] = lambda: mock_svc
        try:
            response = client.post(
                "/v1/documents/upload",
                files={"file": ("manual.pdf", BytesIO(_PDF_MAGIC + b"content"), "application/pdf")},
            )
        finally:
            del client.app.dependency_overrides[get_ingestion_service]

        data = response.json()
        assert data["document_id"] == "abc-123"
        assert data["status"] == "PENDING"

    def test_returns_422_for_invalid_file_type(self, client: TestClient):
        mock_svc = _mock_service()
        mock_svc.upload.side_effect = InvalidFileTypeError("evil.exe")

        from app.api.dependencies import get_ingestion_service

        client.app.dependency_overrides[get_ingestion_service] = lambda: mock_svc
        try:
            response = client.post(
                "/v1/documents/upload",
                files={"file": ("evil.exe", BytesIO(b"MZ garbage"), "application/octet-stream")},
            )
        finally:
            del client.app.dependency_overrides[get_ingestion_service]

        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "INVALID_FILE_TYPE"

    def test_returns_422_for_file_too_large(self, client: TestClient):
        mock_svc = _mock_service()
        mock_svc.upload.side_effect = FileTooLargeError("big.pdf", size_mb=75.0, max_mb=50)

        from app.api.dependencies import get_ingestion_service

        client.app.dependency_overrides[get_ingestion_service] = lambda: mock_svc
        try:
            response = client.post(
                "/v1/documents/upload",
                files={"file": ("big.pdf", BytesIO(_PDF_MAGIC + b"x"), "application/pdf")},
            )
        finally:
            del client.app.dependency_overrides[get_ingestion_service]

        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "FILE_TOO_LARGE"

    def test_returns_409_for_duplicate(self, client: TestClient):
        mock_svc = _mock_service()
        mock_svc.upload.side_effect = DocumentAlreadyExistsError("existing-id", "manual.pdf")

        from app.api.dependencies import get_ingestion_service

        client.app.dependency_overrides[get_ingestion_service] = lambda: mock_svc
        try:
            response = client.post(
                "/v1/documents/upload",
                files={"file": ("manual.pdf", BytesIO(_PDF_MAGIC + b"dup"), "application/pdf")},
            )
        finally:
            del client.app.dependency_overrides[get_ingestion_service]

        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "DOCUMENT_ALREADY_EXISTS"


# ── List tests ─────────────────────────────────────────────────────────────────


class TestListDocumentsEndpoint:
    def test_returns_200_with_empty_list(self, client: TestClient):
        mock_svc = _mock_service()
        mock_svc.list_documents.return_value = DocumentListResponse(documents=[], total=0)

        from app.api.dependencies import get_ingestion_service

        client.app.dependency_overrides[get_ingestion_service] = lambda: mock_svc
        try:
            response = client.get("/v1/documents")
        finally:
            del client.app.dependency_overrides[get_ingestion_service]

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["documents"] == []

    def test_returns_documents_list(self, client: TestClient):
        mock_svc = _mock_service()
        records = [_make_record("doc-001"), _make_record("doc-002")]
        mock_svc.list_documents.return_value = DocumentListResponse(
            documents=records, total=len(records)
        )

        from app.api.dependencies import get_ingestion_service

        client.app.dependency_overrides[get_ingestion_service] = lambda: mock_svc
        try:
            response = client.get("/v1/documents")
        finally:
            del client.app.dependency_overrides[get_ingestion_service]

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["documents"]) == 2


# ── Get by ID tests ────────────────────────────────────────────────────────────


class TestGetDocumentEndpoint:
    def test_returns_200_for_existing_document(self, client: TestClient):
        mock_svc = _mock_service()
        mock_svc.get_document.return_value = _make_record("doc-001")

        from app.api.dependencies import get_ingestion_service

        client.app.dependency_overrides[get_ingestion_service] = lambda: mock_svc
        try:
            response = client.get("/v1/documents/doc-001")
        finally:
            del client.app.dependency_overrides[get_ingestion_service]

        assert response.status_code == 200
        assert response.json()["document_id"] == "doc-001"

    def test_returns_404_for_missing_document(self, client: TestClient):
        mock_svc = _mock_service()
        mock_svc.get_document.side_effect = DocumentNotFoundError("missing-id")

        from app.api.dependencies import get_ingestion_service

        client.app.dependency_overrides[get_ingestion_service] = lambda: mock_svc
        try:
            response = client.get("/v1/documents/missing-id")
        finally:
            del client.app.dependency_overrides[get_ingestion_service]

        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "DOCUMENT_NOT_FOUND"


# ── Delete tests ───────────────────────────────────────────────────────────────


class TestDeleteDocumentEndpoint:
    def test_returns_204_on_success(self, client: TestClient):
        mock_svc = _mock_service()
        mock_svc.delete_document.return_value = None

        from app.api.dependencies import get_ingestion_service

        client.app.dependency_overrides[get_ingestion_service] = lambda: mock_svc
        try:
            response = client.delete("/v1/documents/doc-001")
        finally:
            del client.app.dependency_overrides[get_ingestion_service]

        assert response.status_code == 204

    def test_returns_404_for_missing_document(self, client: TestClient):
        mock_svc = _mock_service()
        mock_svc.delete_document.side_effect = DocumentNotFoundError("ghost-id")

        from app.api.dependencies import get_ingestion_service

        client.app.dependency_overrides[get_ingestion_service] = lambda: mock_svc
        try:
            response = client.delete("/v1/documents/ghost-id")
        finally:
            del client.app.dependency_overrides[get_ingestion_service]

        assert response.status_code == 404
