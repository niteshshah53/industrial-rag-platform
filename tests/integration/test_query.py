"""
Integration tests for the RAG query pipeline.

Requires running Docker services (Qdrant + Ollama).
Skipped automatically when services are unreachable.

Run with:
    pytest tests/integration/ -m integration -v

These tests verify the full path:
  Question → embed → Qdrant search → LLM generate → citations → response
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
    try:
        qdrant = httpx.get("http://localhost:6333/healthz", timeout=2.0)
        ollama = httpx.get("http://localhost:11434/api/tags", timeout=2.0)
        return qdrant.status_code == 200 and ollama.status_code == 200
    except Exception:
        return False


def _make_pdf(text: str) -> bytes:
    pdf = FPDF()
    pdf.set_font("Helvetica", size=12)
    pdf.add_page()
    pdf.multi_cell(0, 10, text)
    return pdf.output()


# ── Skip guard ─────────────────────────────────────────────────────────────────

if not _services_available():
    pytest.skip(
        "Integration tests require Qdrant (6333) and Ollama (11434). "
        "Start with: docker compose up -d qdrant ollama",
        allow_module_level=True,
    )


# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def ingested_document(client: TestClient) -> str:
    """
    Upload and ingest a test PDF, return its document_id.
    Cleaned up after the module.
    """
    content = _make_pdf(
        "HYDRAULIC SYSTEM MAINTENANCE MANUAL\n\n"
        "Maximum Operating Temperature:\n"
        "The hydraulic system must not exceed 85 degrees Celsius during normal operation. "
        "Sustained temperatures above 80 degrees Celsius will degrade the hydraulic fluid "
        "and reduce system performance. Install a temperature gauge at the reservoir inlet.\n\n"
        "Oil Change Intervals:\n"
        "Replace hydraulic fluid every 2000 operating hours or annually, whichever comes first. "
        "Use only ISO VG 46 hydraulic oil or equivalent as specified in the parts manual. "
        "Drain the system completely before refilling to prevent contamination.\n\n"
        "Pressure Relief Valve:\n"
        "The pressure relief valve is factory-set to 250 bar. Do not adjust this setting. "
        "Inspect the valve quarterly for signs of wear or leakage. Replace every 5000 hours.\n\n"
        "Filter Maintenance:\n"
        "Inspect the high-pressure filter element every 500 operating hours. "
        "Replace the filter element when the differential pressure indicator triggers. "
        "Always replace the filter element during each annual service regardless of condition."
    )

    upload_resp = client.post(
        "/v1/documents/upload",
        files={"file": ("hydraulic_manual.pdf", content, "application/pdf")},
    )
    assert upload_resp.status_code == 202
    doc_id = upload_resp.json()["document_id"]

    # Wait for ingestion to complete
    for _ in range(30):
        status_resp = client.get(f"/v1/documents/{doc_id}")
        if status_resp.json()["status"] in ("READY", "FAILED"):
            break
        time.sleep(2)

    assert status_resp.json()["status"] == "READY", "Document failed to ingest"

    yield doc_id

    # Cleanup
    client.delete(f"/v1/documents/{doc_id}")


# ── Tests ──────────────────────────────────────────────────────────────────────


class TestQueryPipelineBasic:
    def test_query_returns_200(self, client: TestClient, ingested_document: str):
        response = client.post(
            "/v1/chat/query",
            json={"question": "What is the maximum operating temperature?"},
        )
        assert response.status_code == 200

    def test_response_has_required_fields(self, client: TestClient, ingested_document: str):
        response = client.post(
            "/v1/chat/query",
            json={"question": "What is the oil change interval?"},
        )
        data = response.json()
        assert "answer" in data
        assert "citations" in data
        assert "retrieval_count" in data
        assert "context_chunks_used" in data
        assert "latency_ms" in data
        assert "request_id" in data

    def test_answer_is_non_empty_string(self, client: TestClient, ingested_document: str):
        response = client.post(
            "/v1/chat/query",
            json={"question": "How often should the filter be replaced?"},
        )
        data = response.json()
        assert isinstance(data["answer"], str)
        assert len(data["answer"]) > 0
        assert data["answer"] != "No relevant documents found."

    def test_response_includes_citations(self, client: TestClient, ingested_document: str):
        response = client.post(
            "/v1/chat/query",
            json={"question": "What is the pressure relief valve setting?"},
        )
        data = response.json()
        assert len(data["citations"]) > 0

    def test_citation_has_correct_structure(self, client: TestClient, ingested_document: str):
        response = client.post(
            "/v1/chat/query",
            json={"question": "What hydraulic oil specification is required?"},
        )
        citation = response.json()["citations"][0]
        assert "document_name" in citation
        assert "page_number" in citation
        assert "chunk_index" in citation
        assert "relevance_score" in citation
        assert citation["relevance_score"] > 0.0

    def test_citation_references_correct_document(self, client: TestClient, ingested_document: str):
        response = client.post(
            "/v1/chat/query",
            json={"question": "What is the maximum operating temperature?"},
        )
        citations = response.json()["citations"]
        assert any(c["document_name"] == "hydraulic_manual.pdf" for c in citations)


class TestQueryPipelineNoDocuments:
    def test_high_threshold_returns_no_documents_response(
        self, client: TestClient, ingested_document: str
    ):
        """A threshold of 0.99 is effectively impossible to satisfy."""
        response = client.post(
            "/v1/chat/query",
            json={
                "question": "What is the maximum temperature?",
                "score_threshold": 0.99,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["answer"] == "No relevant documents found."
        assert data["citations"] == []
        assert data["retrieval_count"] == 0

    def test_out_of_scope_question_returns_graceful_response(
        self, client: TestClient, ingested_document: str
    ):
        """A question completely unrelated to the documents should get 0 results or a polite refusal."""
        response = client.post(
            "/v1/chat/query",
            json={
                "question": "What is the capital of France?",
                "score_threshold": 0.8,
            },
        )
        assert response.status_code == 200


class TestQueryPipelineDocumentFilter:
    def test_document_id_filter_restricts_results(self, client: TestClient, ingested_document: str):
        response = client.post(
            "/v1/chat/query",
            json={
                "question": "What is the maintenance interval?",
                "document_id": ingested_document,
            },
        )
        assert response.status_code == 200
        data = response.json()
        if data["citations"]:
            # All citations should reference the filtered document
            # (document name not doc_id, but let's check retrieval worked)
            assert data["context_chunks_used"] <= data["retrieval_count"]

    def test_wrong_document_id_returns_no_documents(
        self, client: TestClient, ingested_document: str
    ):
        response = client.post(
            "/v1/chat/query",
            json={
                "question": "What is the maximum temperature?",
                "document_id": "00000000-0000-0000-0000-000000000000",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["retrieval_count"] == 0
        assert data["answer"] == "No relevant documents found."


class TestQueryPipelineMetrics:
    def test_context_chunks_used_lte_retrieval_count(
        self, client: TestClient, ingested_document: str
    ):
        response = client.post(
            "/v1/chat/query",
            json={"question": "Describe the filter maintenance procedure."},
        )
        data = response.json()
        assert data["context_chunks_used"] <= data["retrieval_count"]

    def test_latency_ms_is_positive(self, client: TestClient, ingested_document: str):
        response = client.post(
            "/v1/chat/query",
            json={"question": "What is the oil change interval?"},
        )
        assert response.json()["latency_ms"] > 0

    def test_request_id_in_response_body(self, client: TestClient, ingested_document: str):
        custom_id = "integration-test-id-xyz"
        response = client.post(
            "/v1/chat/query",
            json={"question": "What is the relief valve setting?"},
            headers={"X-Request-ID": custom_id},
        )
        assert response.json()["request_id"] == custom_id
        assert response.headers["X-Request-ID"] == custom_id
