# ============================================================
# Industrial RAG Platform — Dockerfile
# ============================================================
# Single-stage build for Phase 0–4 development.
# Multi-stage production build is introduced in Phase 5.
#
# Dependency layer is cached separately from application code
# so that code changes do not invalidate the pip cache.
# ============================================================

FROM python:3.12-slim

# Install uv — fast Python package manager
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Python runtime configuration
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Install into the system Python (no virtualenv inside container)
    UV_SYSTEM_PYTHON=1 \
    # Pre-compile .pyc files at install time
    UV_COMPILE_BYTECODE=1

# ── Dependency layer (cached unless pyproject.toml changes) ──
COPY pyproject.toml .
RUN uv pip install -e . --no-cache

# ── Application code ──────────────────────────────────────────
COPY app/ ./app/
COPY scripts/ ./scripts/
COPY evaluation/ ./evaluation/

# Ensure upload directory exists inside the container.
# In Docker Compose this is replaced by a bind mount.
RUN mkdir -p uploads

EXPOSE 8000

# Production command — no reload, warnings-only uvicorn access log.
# Development overrides this with --reload via docker-compose.yml.
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--log-level", "warning"]
