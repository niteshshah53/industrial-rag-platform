"""
Qdrant client factory.

Provides a single function that constructs a QdrantClient from Settings,
preferring gRPC for bulk upserts and falling back to HTTP for compatibility.

Why a factory function rather than a module-level singleton?
  - Avoids import-time side effects (no connection on import)
  - Enables easy swapping in tests via dependency injection
  - Makes the dependency on Settings explicit
"""

from qdrant_client import QdrantClient

from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def get_qdrant_client(settings: Settings) -> QdrantClient:
    """
    Construct and return a QdrantClient configured from Settings.

    Uses gRPC when qdrant_grpc_port is non-zero for higher throughput
    on bulk vector upserts. Falls back to HTTP-only mode otherwise.

    Args:
        settings: Application settings containing Qdrant connection details.

    Returns:
        Configured QdrantClient instance. Connection is lazy — no network
        call is made until the first operation.
    """
    client = QdrantClient(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
        grpc_port=settings.qdrant_grpc_port,
        prefer_grpc=settings.qdrant_grpc_port > 0,
    )

    logger.debug(
        "Qdrant client created",
        extra={
            "host": settings.qdrant_host,
            "port": settings.qdrant_port,
            "grpc_port": settings.qdrant_grpc_port,
        },
    )

    return client
