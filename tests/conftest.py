"""
Shared pytest fixtures for the Industrial RAG Platform test suite.

Fixtures defined here are available to all tests without explicit import.
Test-specific fixtures belong in the relevant test file.

Fixture scopes:
  session  — created once per test session (expensive resources)
  module   — created once per test module
  function — created fresh for each test (default; safest)

Test settings override production defaults so tests:
  - Never write to the production upload directory
  - Use WARNING log level to reduce noise
  - Can be run without a live Docker environment (unit tests)
"""

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import app

# ── Settings ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    """
    Settings instance configured for the test environment.

    Overrides:
      - upload_dir points to a temp-like path that won't conflict with dev data
      - log_level is WARNING to reduce test output noise
      - log_format is text for readable pytest output

    All other values use defaults from the Settings class.
    """
    return Settings(
        app_env="test",
        log_level="WARNING",
        log_format="text",
        upload_dir="./test_uploads",
        # Keep defaults for service URLs so integration tests
        # can connect to locally running Docker services.
        ollama_base_url="http://localhost:11434",
        qdrant_host="localhost",
        qdrant_port=6333,
    )


# ── HTTP Client ───────────────────────────────────────────────────────────────


@pytest.fixture
def client(test_settings: Settings) -> TestClient:
    """
    FastAPI TestClient with test settings injected.

    Uses FastAPI's dependency_overrides mechanism so get_settings()
    returns test_settings in all routes and dependencies during the test.

    The override is cleared after each test to prevent state leakage.
    """
    app.dependency_overrides[get_settings] = lambda: test_settings

    with TestClient(app, raise_server_exceptions=True) as test_client:
        yield test_client

    app.dependency_overrides.clear()


# ── Phase 1+ fixtures (added when services exist) ─────────────────────────────
#
# @pytest.fixture
# def mock_qdrant_repository():
#     """Mock QdrantRepository for unit tests that don't need a real Qdrant."""
#     ...
#
# @pytest.fixture
# def mock_embedder():
#     """Mock Embedder that returns deterministic 768-dim zero vectors."""
#     ...
#
# @pytest.fixture
# def sample_pdf_path(tmp_path) -> Path:
#     """Path to a small test PDF file."""
#     ...
