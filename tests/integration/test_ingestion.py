"""
Integration tests for the full ingestion pipeline.

Requires a running Docker environment with Qdrant and Ollama.
Skipped automatically if Docker services are not available.

Run with:
    pytest tests/integration/ -m integration -v

These tests verify the full path:
  Upload PDF → Extract → Chunk → Embed → Upsert → READY status
"""

import time

import httpx
import pytest
from fastapi.testclient import TestClient
from fpdf import FPDF

# ── Markers ────────────────────────────────────────────────────────────────────

pytestmark = pytest.mark.integration


# ── Helpers ────────────────────────────────────────────────────────────────────


def _services_available() -> bool:
    """Return True only if both Qdrant and Ollama are reachable."""
    try:
        qdrant = httpx.get("http://localhost:6333/healthz", timeout=2.0)
        ollama = httpx.get("http://localhost:11434/api/tags", timeout=2.0)
        return qdrant.status_code == 200 and ollama.status_code == 200
    except Exception:
        return False


def _make_pdf(text: str) -> bytes:
    """Generate a minimal valid PDF with the given text."""
    pdf = FPDF()
    pdf.set_font("Helvetica", size=12)
    pdf.add_page()
    pdf.multi_cell(0, 10, text)
    return pdf.output()


# ── Skip guard ─────────────────────────────────────────────────────────────────

if not _services_available():
    pytest.skip(
        "Integration tests require Qdrant (6333) and Ollama (11434) to be running. "
        "Start them with: docker compose up -d qdrant ollama",
        allow_module_level=True,
    )


# ── Tests ──────────────────────────────────────────────────────────────────────


class TestFullIngestionPipeline:
    def test_upload_returns_202_with_pending_status(self, client: TestClient):
        content = _make_pdf(
            "This is a maintenance manual for industrial equipment. "
            "It contains safety warnings and operational procedures. " * 5
        )
        response = client.post(
            "/v1/documents/upload",
            files={"file": ("integration_test.pdf", content, "application/pdf")},
        )
        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "PENDING"
        assert "document_id" in data

        # Clean up
        doc_id = data["document_id"]
        client.delete(f"/v1/documents/{doc_id}")

    def test_document_transitions_to_ready(self, client: TestClient):
        """Upload a PDF and wait for it to reach READY status."""
        content = _make_pdf(
            "Hydraulic system maintenance guide. "
            "Replace fluid every 2000 operating hours. "
            "Check pressure relief valve quarterly. " * 10
        )
        upload_resp = client.post(
            "/v1/documents/upload",
            files={"file": ("hydraulic_guide.pdf", content, "application/pdf")},
        )
        assert upload_resp.status_code == 202
        doc_id = upload_resp.json()["document_id"]

        # Poll for completion (max 60s)
        final_status = None
        for _ in range(30):
            get_resp = client.get(f"/v1/documents/{doc_id}")
            assert get_resp.status_code == 200
            status = get_resp.json()["status"]
            if status in ("READY", "FAILED"):
                final_status = status
                break
            time.sleep(2)

        assert final_status == "READY", f"Expected READY but got {final_status}"
        record = client.get(f"/v1/documents/{doc_id}").json()
        assert record["chunk_count"] > 0

        # Clean up
        client.delete(f"/v1/documents/{doc_id}")

    def test_duplicate_upload_returns_409(self, client: TestClient):
        content = _make_pdf("Unique content for duplicate detection test.")

        resp1 = client.post(
            "/v1/documents/upload",
            files={"file": ("dedup_test.pdf", content, "application/pdf")},
        )
        assert resp1.status_code == 202
        doc_id = resp1.json()["document_id"]

        resp2 = client.post(
            "/v1/documents/upload",
            files={"file": ("dedup_test_copy.pdf", content, "application/pdf")},
        )
        assert resp2.status_code == 409
        assert resp2.json()["detail"]["code"] == "DOCUMENT_ALREADY_EXISTS"

        # Clean up
        client.delete(f"/v1/documents/{doc_id}")

    def test_delete_removes_document_from_registry(self, client: TestClient):
        content = _make_pdf("Document to be deleted after upload.")
        upload_resp = client.post(
            "/v1/documents/upload",
            files={"file": ("to_delete.pdf", content, "application/pdf")},
        )
        doc_id = upload_resp.json()["document_id"]

        delete_resp = client.delete(f"/v1/documents/{doc_id}")
        assert delete_resp.status_code == 204

        get_resp = client.get(f"/v1/documents/{doc_id}")
        assert get_resp.status_code == 404

    def test_list_documents_includes_uploaded(self, client: TestClient):
        content = _make_pdf("Listing test document content.")
        upload_resp = client.post(
            "/v1/documents/upload",
            files={"file": ("list_test.pdf", content, "application/pdf")},
        )
        doc_id = upload_resp.json()["document_id"]

        list_resp = client.get("/v1/documents")
        assert list_resp.status_code == 200
        doc_ids = [d["document_id"] for d in list_resp.json()["documents"]]
        assert doc_id in doc_ids

        # Clean up
        client.delete(f"/v1/documents/{doc_id}")
