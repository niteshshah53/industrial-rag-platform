"""
Qdrant vector store repository.

Responsibilities:
  - Create and verify the documents collection on startup
  - Upsert chunk vectors with ChunkPayload metadata
  - Search vectors with score threshold and optional document_id filter
  - Delete all vectors belonging to a document
  - Thin wrapper: no business logic, only data access

Design decisions:
  - Synchronous QdrantClient methods are used throughout.
    IngestionService and QueryService wrap calls in run_in_executor.
  - CollectionDimensionMismatchError is raised at startup if an existing
    collection has the wrong vector size. This requires operator action
    (delete the collection or fix EMBEDDING_DIMENSIONS). The app refuses
    to start in this case rather than silently producing bad search results.
  - Batch upsert via qdrant_client.upsert with PointStruct list — efficient
    for bulk ingestion.
  - query_points() applies score_threshold server-side via Qdrant's built-in
    score_threshold parameter — avoids fetching and discarding low-quality
    results over the network.
"""

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
)

from app.core.exceptions import CollectionDimensionMismatchError, ServiceUnavailableError
from app.core.logging import get_logger
from app.core.models import ChunkPayload, DocumentChunk, RetrievedChunk

logger = get_logger(__name__)


class QdrantRepository:
    """
    Manages vector storage for document chunks in Qdrant.

    Args:
        client: Configured QdrantClient instance.
        collection_name: Name of the Qdrant collection to use.
        vector_size: Dimensionality of embedding vectors (must match model output).
    """

    def __init__(
        self,
        client: QdrantClient,
        collection_name: str,
        vector_size: int,
    ) -> None:
        self._client = client
        self._collection_name = collection_name
        self._vector_size = vector_size

    def ensure_collection_exists(self) -> None:
        """
        Create the collection if it does not exist, or verify dimensions match.

        Called once at application startup. Raises CollectionDimensionMismatchError
        if an existing collection was built with a different vector size — this
        requires operator intervention.

        Raises:
            CollectionDimensionMismatchError: Existing collection has wrong dimensions.
            ServiceUnavailableError: Qdrant is not reachable.
        """
        try:
            collections = self._client.get_collections().collections
            existing_names = {c.name for c in collections}

            if self._collection_name in existing_names:
                self._verify_dimensions()
                logger.debug(
                    "Qdrant collection already exists",
                    extra={"collection": self._collection_name},
                )
            else:
                self._create_collection()

        except (CollectionDimensionMismatchError, ServiceUnavailableError):
            raise
        except Exception as exc:
            raise ServiceUnavailableError("qdrant", detail=str(exc)) from exc

    def upsert_chunks(
        self,
        chunks: list[DocumentChunk],
        vectors: list[list[float]],
    ) -> None:
        """
        Upsert chunk vectors with their payloads into Qdrant.

        Args:
            chunks: DocumentChunk objects (provides metadata for payload).
            vectors: Embedding vectors, one per chunk, in the same order.
        """
        if not chunks:
            return

        points = [
            PointStruct(
                id=chunk.chunk_id,
                vector=vector,
                payload=ChunkPayload(
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    filename=chunk.filename,
                    page_number=chunk.page_number,
                    chunk_index=chunk.chunk_index,
                    text=chunk.text,
                ).model_dump(),
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]

        self._client.upsert(collection_name=self._collection_name, points=points)

        logger.debug(
            "Chunks upserted to Qdrant",
            extra={
                "collection": self._collection_name,
                "chunk_count": len(points),
                "document_id": chunks[0].document_id if chunks else None,
            },
        )

    def search(
        self,
        vector: list[float],
        top_k: int,
        score_threshold: float,
        document_id_filter: str | None = None,
    ) -> list[RetrievedChunk]:
        """
        Search for the closest chunks to a query vector.

        Args:
            vector: Query embedding produced by the embedding model.
            top_k: Maximum number of results to return.
            score_threshold: Minimum cosine similarity for a chunk to be included.
                             Applied server-side by Qdrant to avoid network overhead.
            document_id_filter: If set, restrict search to chunks from this document.

        Returns:
            List of RetrievedChunk objects sorted by score descending.
            Empty list when no chunks meet the threshold.
        """
        query_filter = None
        if document_id_filter:
            query_filter = Filter(
                must=[
                    FieldCondition(
                        key="document_id",
                        match=MatchValue(value=document_id_filter),
                    )
                ]
            )

        response = self._client.query_points(
            collection_name=self._collection_name,
            query=vector,
            query_filter=query_filter,
            limit=top_k,
            score_threshold=score_threshold,
            with_payload=True,
        )

        chunks = [
            RetrievedChunk(
                chunk_id=r.payload["chunk_id"],
                text=r.payload["text"],
                score=r.score,
                document_id=r.payload["document_id"],
                filename=r.payload["filename"],
                page_number=r.payload["page_number"],
                chunk_index=r.payload["chunk_index"],
            )
            for r in response.points
        ]

        logger.debug(
            "Qdrant search complete",
            extra={
                "collection": self._collection_name,
                "top_k": top_k,
                "score_threshold": score_threshold,
                "results_count": len(chunks),
                "document_id_filter": document_id_filter,
            },
        )

        return chunks

    def delete_document(self, document_id: str) -> None:
        """
        Delete all vectors belonging to a document.

        Args:
            document_id: The document UUID whose vectors should be removed.
        """
        self._client.delete(
            collection_name=self._collection_name,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="document_id",
                        match=MatchValue(value=document_id),
                    )
                ]
            ),
        )

        logger.debug(
            "Document vectors deleted from Qdrant",
            extra={"collection": self._collection_name, "document_id": document_id},
        )

    def _create_collection(self) -> None:
        """Create the collection with the configured vector parameters."""
        self._client.create_collection(
            collection_name=self._collection_name,
            vectors_config=VectorParams(
                size=self._vector_size,
                distance=Distance.COSINE,
            ),
        )
        # Index document_id as KEYWORD for O(1) filtered deletes and searches.
        self._client.create_payload_index(
            collection_name=self._collection_name,
            field_name="document_id",
            field_schema=PayloadSchemaType.KEYWORD,
        )
        logger.info(
            "Qdrant collection created",
            extra={
                "collection": self._collection_name,
                "vector_size": self._vector_size,
            },
        )

    def _verify_dimensions(self) -> None:
        """
        Check that the existing collection has the expected vector size.

        Raises:
            CollectionDimensionMismatchError: Dimensions differ.
        """
        info = self._client.get_collection(self._collection_name)
        existing_size = info.config.params.vectors.size  # type: ignore[union-attr]

        if existing_size != self._vector_size:
            raise CollectionDimensionMismatchError(
                collection=self._collection_name,
                existing_dim=existing_size,
                configured_dim=self._vector_size,
            )
