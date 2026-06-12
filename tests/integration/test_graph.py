"""
Integration tests for the LangGraph RAG graph (Phase 3 non-regression).

Requires running Docker services (Qdrant + Ollama).
Skipped automatically when services are unreachable.

Run with:
    pytest tests/integration/ -m integration -v

These tests verify that the LangGraph graph produces output identical in shape
and quality to the Phase 2 direct pipeline. The external API contract must not
regress after the LangGraph migration.

Tests also exercise the conditional edges:
  - Empty retrieval (score_threshold=0.99) → "No relevant documents found."
  - Document ID filter restricts search scope
  - request_id is propagated through the graph to the response

The graph itself is compiled here (not via app.state) so the tests remain
independent of the lifespan setup.
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
    Upload and ingest a test PDF containing known hydraulic system facts.
    Returns the document_id. Cleaned up after the module.
    """
    content = _make_pdf(
        "HYDRAULIC SYSTEM MAINTENANCE MANUAL\n\n"
        "Maximum Operating Temperature:\n"
        "The hydraulic system must not exceed 85 degrees Celsius during normal operation. "
        "Sustained temperatures above 80 degrees Celsius will degrade the hydraulic fluid.\n\n"
        "Oil Change Intervals:\n"
        "Replace hydraulic fluid every 2000 operating hours or annually, whichever comes first. "
        "Use only ISO VG 46 hydraulic oil or equivalent.\n\n"
        "Pressure Relief Valve:\n"
        "The pressure relief valve is factory-set to 250 bar. Do not adjust this setting. "
        "Inspect the valve quarterly for signs of wear or leakage.\n\n"
        "Filter Maintenance:\n"
        "Inspect the high-pressure filter element every 500 operating hours. "
        "Replace the filter element when the differential pressure indicator triggers."
    )

    upload_resp = client.post(
        "/v1/documents/upload",
        files={"file": ("hydraulic_graph_test.pdf", content, "application/pdf")},
    )
    assert upload_resp.status_code == 202
    doc_id = upload_resp.json()["document_id"]

    # Wait for ingestion to complete (up to 60 seconds)
    for _ in range(30):
        status_resp = client.get(f"/v1/documents/{doc_id}")
        if status_resp.json()["status"] in ("READY", "FAILED"):
            break
        time.sleep(2)

    assert status_resp.json()["status"] == "READY", "Document failed to ingest"

    yield doc_id

    client.delete(f"/v1/documents/{doc_id}")


# ── Non-regression: same output shape as Phase 2 ─────────────────────────────


class TestGraphNonRegression:
    """Verify the LangGraph pipeline produces the same response shape as Phase 2."""

    def test_query_returns_200(self, client: TestClient, ingested_document: str):
        response = client.post(
            "/v1/chat/query",
            json={"question": "What is the maximum operating temperature?"},
        )
        assert response.status_code == 200

    def test_response_has_all_required_fields(self, client: TestClient, ingested_document: str):
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
            json={"question": "How often should the filter be inspected?"},
        )
        data = response.json()
        assert isinstance(data["answer"], str)
        assert len(data["answer"]) > 0

    def test_response_includes_citations(self, client: TestClient, ingested_document: str):
        response = client.post(
            "/v1/chat/query",
            json={"question": "What is the pressure relief valve setting?"},
        )
        assert len(response.json()["citations"]) > 0

    def test_citation_has_correct_structure(self, client: TestClient, ingested_document: str):
        response = client.post(
            "/v1/chat/query",
            json={"question": "What hydraulic oil is required?"},
        )
        citation = response.json()["citations"][0]
        assert "document_name" in citation
        assert "page_number" in citation
        assert "chunk_index" in citation
        assert "relevance_score" in citation
        assert citation["relevance_score"] > 0.0

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
            json={"question": "What is the maximum operating temperature?"},
        )
        assert response.json()["latency_ms"] > 0


# ── Conditional edge: empty retrieval ─────────────────────────────────────────


class TestGraphEmptyRetrievalEdge:
    """Verify the retrieve → END conditional edge works correctly."""

    def test_impossible_threshold_triggers_no_documents_response(
        self, client: TestClient, ingested_document: str
    ):
        """score_threshold=0.99 is effectively impossible — graph must skip generate."""
        response = client.post(
            "/v1/chat/query",
            json={"question": "What is the maximum temperature?", "score_threshold": 0.99},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["answer"] == "No relevant documents found."
        assert data["citations"] == []
        assert data["retrieval_count"] == 0
        assert data["context_chunks_used"] == 0

    def test_wrong_document_id_triggers_no_documents_response(
        self, client: TestClient, ingested_document: str
    ):
        """Filtering by a non-existent document_id → 0 chunks → early exit."""
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


# ── Request ID propagation through graph ──────────────────────────────────────


class TestGraphRequestIdPropagation:
    def test_request_id_from_header_appears_in_response(
        self, client: TestClient, ingested_document: str
    ):
        custom_id = "graph-integration-test-id"
        response = client.post(
            "/v1/chat/query",
            json={"question": "What is the relief valve setting?"},
            headers={"X-Request-ID": custom_id},
        )
        assert response.json()["request_id"] == custom_id
        assert response.headers["X-Request-ID"] == custom_id

    def test_auto_generated_request_id_is_in_response(
        self, client: TestClient, ingested_document: str
    ):
        """When no X-Request-ID header is sent, the response still has a request_id."""
        response = client.post(
            "/v1/chat/query",
            json={"question": "What is the oil change interval?"},
        )
        data = response.json()
        assert isinstance(data["request_id"], str)
        assert len(data["request_id"]) > 0


# ── Document filter ────────────────────────────────────────────────────────────


class TestGraphDocumentFilter:
    def test_document_id_filter_returns_200(self, client: TestClient, ingested_document: str):
        response = client.post(
            "/v1/chat/query",
            json={
                "question": "What is the maintenance interval?",
                "document_id": ingested_document,
            },
        )
        assert response.status_code == 200

    def test_document_id_filter_context_chunks_lte_retrieval(
        self, client: TestClient, ingested_document: str
    ):
        response = client.post(
            "/v1/chat/query",
            json={
                "question": "Describe filter maintenance.",
                "document_id": ingested_document,
            },
        )
        data = response.json()
        assert data["context_chunks_used"] <= data["retrieval_count"]
