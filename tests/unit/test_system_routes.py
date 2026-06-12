"""
Unit tests for system router endpoints.

Tests liveness, readiness (mocked), and metrics endpoints.
No Docker required — external service calls are mocked.
"""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient


class TestLiveness:
    """GET /v1/health/live always returns 200."""

    def test_returns_200(self, client: TestClient):
        response = client.get("/v1/health/live")
        assert response.status_code == 200

    def test_response_body(self, client: TestClient):
        response = client.get("/v1/health/live")
        assert response.json() == {"status": "ok"}

    def test_does_not_call_external_services(self, client: TestClient):
        """Liveness must never check Ollama or Qdrant — no external I/O."""
        with patch("httpx.AsyncClient") as mock_client:
            client.get("/v1/health/live")
            mock_client.assert_not_called()


class TestReadiness:
    """GET /v1/health/ready checks external services."""

    def test_returns_200_when_all_services_healthy(self, client: TestClient):
        mock_response = AsyncMock()
        mock_response.status_code = 200

        with patch("app.api.v1.routers.system.httpx.AsyncClient") as mock_http:
            mock_http.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )
            response = client.get("/v1/health/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["services"]["ollama"] is True
        assert data["services"]["qdrant"] is True

    def test_returns_503_when_ollama_unreachable(self, client: TestClient):
        import httpx

        async def mock_get(url, **kwargs):
            if "11434" in url:
                raise httpx.ConnectError("Connection refused")
            mock = AsyncMock()
            mock.status_code = 200
            return mock

        with patch("app.api.v1.routers.system.httpx.AsyncClient") as mock_http:
            mock_http.return_value.__aenter__.return_value.get = mock_get
            response = client.get("/v1/health/ready")

        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "degraded"
        assert data["services"]["ollama"] is False

    def test_returns_503_when_qdrant_unreachable(self, client: TestClient):
        import httpx

        async def mock_get(url, **kwargs):
            if "6333" in url or "healthz" in url:
                raise httpx.ConnectError("Connection refused")
            mock = AsyncMock()
            mock.status_code = 200
            return mock

        with patch("app.api.v1.routers.system.httpx.AsyncClient") as mock_http:
            mock_http.return_value.__aenter__.return_value.get = mock_get
            response = client.get("/v1/health/ready")

        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "degraded"
        assert data["services"]["qdrant"] is False


class TestMetrics:
    """GET /v1/metrics returns counter structure."""

    def test_returns_200(self, client: TestClient):
        response = client.get("/v1/metrics")
        assert response.status_code == 200

    def test_response_contains_expected_fields(self, client: TestClient):
        data = client.get("/v1/metrics").json()
        expected_fields = {
            "documents_total",
            "documents_pending",
            "documents_processing",
            "documents_ready",
            "documents_failed",
            "queries_total",
            "queries_avg_latency_ms",
            "queries_p95_latency_ms",
        }
        assert expected_fields.issubset(data.keys())

    def test_initial_counters_are_zero(self, client: TestClient):
        data = client.get("/v1/metrics").json()
        assert data["documents_total"] == 0
        assert data["queries_total"] == 0


class TestRequestId:
    """X-Request-ID header is propagated through requests."""

    def test_generates_request_id_when_not_provided(self, client: TestClient):
        response = client.get("/v1/health/live")
        assert "X-Request-ID" in response.headers
        assert len(response.headers["X-Request-ID"]) > 0

    def test_echoes_provided_request_id(self, client: TestClient):
        custom_id = "my-test-request-id-123"
        response = client.get("/v1/health/live", headers={"X-Request-ID": custom_id})
        assert response.headers["X-Request-ID"] == custom_id
