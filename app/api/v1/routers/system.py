"""
System router — health probes and runtime metrics.

Endpoints:
  GET /v1/health/live   — liveness probe (always 200 if process is running)
  GET /v1/health/ready  — readiness probe (200 if all dependencies reachable)
  GET /v1/metrics       — runtime counters

Design:
  Liveness and readiness are intentionally separate probes following the
  Kubernetes probe pattern:
    - Liveness:  "is the process alive?" — restarts on failure
    - Readiness: "can it serve traffic?" — removes from rotation on failure

  A single combined health endpoint would cause Kubernetes to restart the
  pod every time Qdrant is briefly unreachable, creating a restart loop.
  Keep them separate.
"""

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.logging import get_logger

router = APIRouter(tags=["system"])
logger = get_logger(__name__)


@router.get(
    "/health/live",
    summary="Liveness probe",
    description=(
        "Returns 200 if the application process is running. "
        "Never checks external dependencies. "
        "Use as a Kubernetes liveness probe."
    ),
)
async def liveness() -> dict:
    """
    Liveness probe endpoint.

    Always returns 200 as long as the process is alive and the event loop
    is processing requests. Does not check Qdrant or Ollama — those checks
    belong in the readiness probe.
    """
    return {"status": "ok"}


@router.get(
    "/health/ready",
    summary="Readiness probe",
    description=(
        "Returns 200 if all external dependencies are reachable. "
        "Returns 503 if any dependency is unavailable. "
        "Use as a Kubernetes readiness probe."
    ),
)
async def readiness() -> JSONResponse:
    """
    Readiness probe endpoint.

    Checks:
      - Ollama API is reachable (GET /api/tags)
      - Qdrant REST API is reachable (GET /healthz)

    Returns 200 with status="ready" if all checks pass.
    Returns 503 with status="degraded" if any check fails.
    The failing service(s) are identified in the response body.
    """
    settings = get_settings()
    service_checks: dict[str, bool] = {}

    # ── Check Ollama ──────────────────────────────────────────────────────────
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(f"{settings.ollama_base_url}/api/tags")
            service_checks["ollama"] = response.status_code == 200
    except Exception as exc:
        logger.warning("Ollama health check failed", extra={"error": str(exc)})
        service_checks["ollama"] = False

    # ── Check Qdrant ──────────────────────────────────────────────────────────
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(f"{settings.qdrant_url}/healthz")
            service_checks["qdrant"] = response.status_code == 200
    except Exception as exc:
        logger.warning("Qdrant health check failed", extra={"error": str(exc)})
        service_checks["qdrant"] = False

    all_healthy = all(service_checks.values())
    http_status = 200 if all_healthy else 503

    body = {
        "status": "ready" if all_healthy else "degraded",
        "services": service_checks,
    }

    if not all_healthy:
        failed = [name for name, ok in service_checks.items() if not ok]
        logger.warning("Readiness check failed", extra={"failed_services": failed})

    return JSONResponse(status_code=http_status, content=body)


@router.get(
    "/metrics",
    summary="Runtime metrics",
    description="Returns basic runtime counters for monitoring.",
)
async def metrics() -> dict:
    """
    Runtime metrics endpoint.

    Returns in-process counters for documents and queries.
    Phase 5 adds p50/p95 latency percentiles and per-status document counts.

    Note: counters reset when the container restarts. For persistent metrics,
    integrate with Prometheus (Phase 5 upgrade path).
    """
    # Placeholder counters — real values are wired in Phase 1 and Phase 2
    # when DocumentRepository and QueryService exist.
    return {
        "documents_total": 0,
        "documents_pending": 0,
        "documents_processing": 0,
        "documents_ready": 0,
        "documents_failed": 0,
        "queries_total": 0,
        "queries_avg_latency_ms": 0.0,
        "queries_p95_latency_ms": 0.0,
    }
