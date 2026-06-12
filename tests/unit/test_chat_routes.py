"""
Unit tests for the chat query API route.

All QueryService calls are mocked. Tests focus on HTTP concerns:
status codes, request/response shape, error propagation.
No Docker required.
"""

from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.core.exceptions import ServiceUnavailableError
from app.core.models import Citation, QueryResponse

# ── Helpers ────────────────────────────────────────────────────────────────────


_DEFAULT_CITATION = Citation(
    document_name="manual.pdf",
    page_number=7,
    chunk_index=12,
    relevance_score=0.84,
)


def _make_response(
    answer: str = "The maximum temperature is 85°C.",
    citations: list | None = None,
    retrieval_count: int = 3,
    context_chunks_used: int = 2,
) -> QueryResponse:
    # Use `is None` guard, not `or`, so an explicit empty list is respected.
    actual_citations = [_DEFAULT_CITATION] if citations is None else citations
    return QueryResponse(
        answer=answer,
        citations=actual_citations,
        retrieval_count=retrieval_count,
        context_chunks_used=context_chunks_used,
        latency_ms=1240.5,
        request_id="test-request-id",
    )


def _mock_service(response: QueryResponse | None = None, side_effect=None):
    svc = MagicMock()
    if side_effect:
        svc.query = AsyncMock(side_effect=side_effect)
    else:
        svc.query = AsyncMock(return_value=response or _make_response())
    return svc


# ── Tests ──────────────────────────────────────────────────────────────────────


class TestQueryEndpoint:
    def test_returns_200_on_success(self, client: TestClient):
        from app.api.dependencies import get_query_service

        mock_svc = _mock_service()
        client.app.dependency_overrides[get_query_service] = lambda: mock_svc
        try:
            response = client.post(
                "/v1/chat/query",
                json={"question": "What is the max temperature?"},
            )
        finally:
            del client.app.dependency_overrides[get_query_service]

        assert response.status_code == 200

    def test_response_contains_required_fields(self, client: TestClient):
        from app.api.dependencies import get_query_service

        mock_svc = _mock_service()
        client.app.dependency_overrides[get_query_service] = lambda: mock_svc
        try:
            response = client.post(
                "/v1/chat/query",
                json={"question": "What is the maintenance interval?"},
            )
        finally:
            del client.app.dependency_overrides[get_query_service]

        data = response.json()
        assert "answer" in data
        assert "citations" in data
        assert "retrieval_count" in data
        assert "context_chunks_used" in data
        assert "latency_ms" in data
        assert "request_id" in data

    def test_answer_is_string(self, client: TestClient):
        from app.api.dependencies import get_query_service

        mock_svc = _mock_service(_make_response(answer="This is the answer."))
        client.app.dependency_overrides[get_query_service] = lambda: mock_svc
        try:
            response = client.post(
                "/v1/chat/query",
                json={"question": "What is the torque specification?"},
            )
        finally:
            del client.app.dependency_overrides[get_query_service]

        assert response.json()["answer"] == "This is the answer."

    def test_no_documents_response_returns_200(self, client: TestClient):
        from app.api.dependencies import get_query_service

        mock_svc = _mock_service(
            _make_response(
                answer="No relevant documents found.",
                citations=[],
                retrieval_count=0,
                context_chunks_used=0,
            )
        )
        client.app.dependency_overrides[get_query_service] = lambda: mock_svc
        try:
            response = client.post(
                "/v1/chat/query",
                json={"question": "Tell me about quantum entanglement."},
            )
        finally:
            del client.app.dependency_overrides[get_query_service]

        assert response.status_code == 200
        data = response.json()
        assert data["answer"] == "No relevant documents found."
        assert data["citations"] == []

    def test_citations_list_in_response(self, client: TestClient):
        from app.api.dependencies import get_query_service

        citations = [
            Citation(
                document_name="manual.pdf",
                page_number=3,
                chunk_index=5,
                relevance_score=0.91,
            )
        ]
        mock_svc = _mock_service(_make_response(citations=citations))
        client.app.dependency_overrides[get_query_service] = lambda: mock_svc
        try:
            response = client.post(
                "/v1/chat/query",
                json={"question": "What does the manual say?"},
            )
        finally:
            del client.app.dependency_overrides[get_query_service]

        data = response.json()
        assert len(data["citations"]) == 1
        assert data["citations"][0]["page_number"] == 3

    def test_returns_503_when_service_unavailable(self, client: TestClient):
        from app.api.dependencies import get_query_service

        mock_svc = _mock_service(side_effect=ServiceUnavailableError("ollama"))
        client.app.dependency_overrides[get_query_service] = lambda: mock_svc
        try:
            response = client.post(
                "/v1/chat/query",
                json={"question": "What is the pressure spec?"},
            )
        finally:
            del client.app.dependency_overrides[get_query_service]

        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "SERVICE_UNAVAILABLE"


class TestQueryRequestValidation:
    def test_empty_question_returns_422(self, client: TestClient):
        from app.api.dependencies import get_query_service

        mock_svc = _mock_service()
        client.app.dependency_overrides[get_query_service] = lambda: mock_svc
        try:
            response = client.post("/v1/chat/query", json={"question": ""})
        finally:
            del client.app.dependency_overrides[get_query_service]

        assert response.status_code == 422

    def test_missing_question_returns_422(self, client: TestClient):
        from app.api.dependencies import get_query_service

        mock_svc = _mock_service()
        client.app.dependency_overrides[get_query_service] = lambda: mock_svc
        try:
            response = client.post("/v1/chat/query", json={"top_k": 5})
        finally:
            del client.app.dependency_overrides[get_query_service]

        assert response.status_code == 422

    def test_question_too_long_returns_422(self, client: TestClient):
        from app.api.dependencies import get_query_service

        mock_svc = _mock_service()
        client.app.dependency_overrides[get_query_service] = lambda: mock_svc
        try:
            response = client.post("/v1/chat/query", json={"question": "x" * 1001})
        finally:
            del client.app.dependency_overrides[get_query_service]

        assert response.status_code == 422

    def test_default_parameters_are_applied(self, client: TestClient):
        from app.api.dependencies import get_query_service

        mock_svc = _mock_service()
        client.app.dependency_overrides[get_query_service] = lambda: mock_svc
        try:
            client.post("/v1/chat/query", json={"question": "Test question."})
        finally:
            del client.app.dependency_overrides[get_query_service]

        call_args = mock_svc.query.call_args
        request_arg = call_args.args[0]
        assert request_arg.top_k == 5
        assert request_arg.score_threshold == 0.6
        assert request_arg.document_id is None

    def test_custom_parameters_forwarded(self, client: TestClient):
        from app.api.dependencies import get_query_service

        mock_svc = _mock_service()
        client.app.dependency_overrides[get_query_service] = lambda: mock_svc
        try:
            client.post(
                "/v1/chat/query",
                json={
                    "question": "Test question.",
                    "top_k": 3,
                    "score_threshold": 0.75,
                    "document_id": "doc-abc",
                },
            )
        finally:
            del client.app.dependency_overrides[get_query_service]

        call_args = mock_svc.query.call_args
        request_arg = call_args.args[0]
        assert request_arg.top_k == 3
        assert request_arg.score_threshold == 0.75
        assert request_arg.document_id == "doc-abc"


class TestQueryRequestIdPropagation:
    def test_request_id_forwarded_to_service(self, client: TestClient):
        from app.api.dependencies import get_query_service

        mock_svc = _mock_service()
        client.app.dependency_overrides[get_query_service] = lambda: mock_svc
        try:
            client.post(
                "/v1/chat/query",
                json={"question": "Test."},
                headers={"X-Request-ID": "my-trace-id"},
            )
        finally:
            del client.app.dependency_overrides[get_query_service]

        call_kwargs = mock_svc.query.call_args.kwargs
        assert call_kwargs.get("request_id") == "my-trace-id"
