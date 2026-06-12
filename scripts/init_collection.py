#!/usr/bin/env python3
"""
init_collection.py — Qdrant collection initialisation script.

Creates the document vector collection in Qdrant with the parameters
specified in application settings. Safe to run multiple times:
  - If the collection does not exist, it is created.
  - If the collection exists with matching parameters, no action is taken.
  - If the collection exists with mismatched dimensions, the script exits
    with an error and does NOT drop the existing collection automatically
    (operator must decide whether to delete data).

Usage:
    # Inside Docker Compose (recommended):
    docker compose exec app python scripts/init_collection.py

    # Locally (requires qdrant-client installed and Qdrant running):
    python scripts/init_collection.py

This script is idempotent. It is also called from the app's startup
lifespan in Phase 1+, but remains available as a standalone script for
operational use.
"""

import sys
from pathlib import Path

# Add project root to sys.path so app.* imports work when running as a script.
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from qdrant_client import QdrantClient  # noqa: E402
from qdrant_client.models import Distance, PayloadSchemaType, VectorParams  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.logging import configure_logging, get_logger  # noqa: E402

configure_logging()
logger = get_logger(__name__)

_DISTANCE_MAP: dict[str, Distance] = {
    "Cosine": Distance.COSINE,
    "Dot": Distance.DOT,
    "Euclidean": Distance.EUCLID,
}


def init_collection() -> None:
    """Create the Qdrant collection if it does not exist with correct parameters."""
    settings = get_settings()

    distance = _DISTANCE_MAP.get(settings.qdrant_distance_metric)
    if distance is None:
        logger.error(
            "Unknown distance metric",
            extra={
                "metric": settings.qdrant_distance_metric,
                "supported": list(_DISTANCE_MAP.keys()),
            },
        )
        sys.exit(1)

    logger.info(
        "Connecting to Qdrant",
        extra={"host": settings.qdrant_host, "port": settings.qdrant_port},
    )

    client = QdrantClient(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
        # Use gRPC for better performance; fall back to REST on failure.
        prefer_grpc=True,
        grpc_port=settings.qdrant_grpc_port,
    )

    collection_name = settings.qdrant_collection_name
    existing_collections = {c.name for c in client.get_collections().collections}

    if collection_name in existing_collections:
        # Verify the existing collection has matching vector dimensions.
        info = client.get_collection(collection_name)
        existing_dim = info.config.params.vectors.size  # type: ignore[union-attr]

        if existing_dim != settings.embedding_dimensions:
            logger.error(
                "Collection dimension mismatch — manual intervention required",
                extra={
                    "collection": collection_name,
                    "existing_dimensions": existing_dim,
                    "configured_dimensions": settings.embedding_dimensions,
                    "resolution": (
                        "Delete the collection via the Qdrant UI or API, "
                        "then re-run this script. WARNING: this deletes all vectors."
                    ),
                },
            )
            sys.exit(1)

        logger.info(
            "Collection already exists with correct parameters — no action needed",
            extra={
                "collection": collection_name,
                "dimensions": existing_dim,
                "distance": settings.qdrant_distance_metric,
            },
        )
        return

    # Collection does not exist — create it.
    client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(
            size=settings.embedding_dimensions,
            distance=distance,
        ),
    )

    # Create a payload index on document_id to enable efficient
    # document-scoped vector searches (used in Phase 2 query filtering).
    client.create_payload_index(
        collection_name=collection_name,
        field_name="document_id",
        field_schema=PayloadSchemaType.KEYWORD,
    )

    logger.info(
        "Qdrant collection created",
        extra={
            "collection": collection_name,
            "dimensions": settings.embedding_dimensions,
            "distance": settings.qdrant_distance_metric,
        },
    )


if __name__ == "__main__":
    init_collection()
