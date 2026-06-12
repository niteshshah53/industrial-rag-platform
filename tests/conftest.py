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


# ── Phase 1 fixtures ──────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def sample_pdf_bytes() -> bytes:
    """
    Generate a minimal valid PDF in memory using fpdf2.

    Session-scoped because PDF generation is deterministic and reusing
    the same bytes across tests avoids the small CPU overhead.

    Returns bytes that pass magic byte validation and contain extractable text.
    """
    from fpdf import FPDF

    pdf = FPDF()
    pdf.set_font("Helvetica", size=12)

    pages = [
        (
            "HYDRAULIC SYSTEM MAINTENANCE MANUAL\n\n"
            "Chapter 1: Safety Warnings\n\n"
            "Always depressurise the hydraulic system before performing maintenance. "
            "Wear appropriate personal protective equipment at all times. "
            "Check all connections for leaks before restarting the system."
        ),
        (
            "Chapter 2: Routine Maintenance Schedule\n\n"
            "Replace hydraulic fluid every 2000 operating hours or annually. "
            "Inspect filter elements every 500 hours. "
            "Check actuator seals for wear every 1000 hours. "
            "Verify relief valve settings quarterly."
        ),
        (
            "Chapter 3: Troubleshooting\n\n"
            "If system pressure drops below nominal, check for: "
            "blocked filter, worn pump, or pressure relief valve malfunction. "
            "If overheating occurs, verify cooler is functioning and oil level is correct."
        ),
    ]

    for page_text in pages:
        pdf.add_page()
        pdf.multi_cell(0, 10, page_text)

    return pdf.output()


@pytest.fixture(scope="session")
def sample_pdf_path(sample_pdf_bytes: bytes, tmp_path_factory) -> str:
    """Write the sample PDF to a temp file and return its path."""
    tmp_dir = tmp_path_factory.mktemp("pdfs")
    pdf_path = tmp_dir / "sample_manual.pdf"
    pdf_path.write_bytes(sample_pdf_bytes)
    return str(pdf_path)
