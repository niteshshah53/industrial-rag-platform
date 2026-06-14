"""
Qdrant vector store repository.

Responsibilities:
  - Create and verify the documents collection on startup
  - Ensure the sparse vector field exists for hybrid search
  - Upsert chunk vectors (dense + optional sparse) with ChunkPayload metadata
  - Dense vector search with score threshold and optional document_id filter
  - Hybrid search: BM25 sparse + dense via Qdrant RRF fusion
  - Delete all vectors belonging to a document

Design decisions:
  - Synchronous QdrantClient methods are used throughout.
    IngestionService and QueryService wrap calls in run_in_executor.
  - CollectionDimensionMismatchError is raised at startup if an existing
    collection has the wrong vector size. This requires operator action.
  - Sparse vector field "text-sparse" is added non-destructively at startup
    via update_collection. Existing dense-only points still work; new uploads
    get both vectors. Re-ingest documents to enable full hybrid search.
  - For hybrid search, score_threshold applies to the dense prefetch only.
    RRF fusion scores are relative ranks, not cosine similarity values.
"""

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    Fusion,
    FusionQuery,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    Prefetch,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)

from app.core.exceptions import CollectionDimensionMismatchError, ServiceUnavailableError
from app.core.logging import get_logger
from app.core.models import ChunkPayload, DocumentChunk, RetrievedChunk

logger = get_logger(__name__)

_SPARSE_VECTOR_NAME = "text-sparse"


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
        Also ensures the sparse vector field is present for hybrid search.

        Called once at application startup. Raises CollectionDimensionMismatchError
        if an existing collection was built with a different vector size.

        Raises:
            CollectionDimensionMismatchError: Existing collection has wrong dimensions.
            ServiceUnavailableError: Qdrant is not reachable.
        """
        try:
            collections = self._client.get_collections().collections
            existing_names = {c.name for c in collections}

            if self._collection_name in existing_names:
                self._verify_dimensions()
                self._ensure_sparse_vector_field()
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
        sparse_vectors: list[SparseVector] | None = None,
    ) -> None:
        """
        Upsert chunk vectors with their payloads into Qdrant.

        When sparse_vectors is provided, each point is stored with both a dense
        vector (under the default unnamed key "") and a sparse BM25 vector (under
        "text-sparse"). Points without sparse_vectors use the legacy dense-only
        format for backward compatibility.

        Args:
            chunks: DocumentChunk objects (provides metadata for payload).
            vectors: Dense embedding vectors, one per chunk, in the same order.
            sparse_vectors: Optional BM25 sparse vectors, one per chunk.
        """
        if not chunks:
            return

        if sparse_vectors is not None:
            points = [
                PointStruct(
                    id=chunk.chunk_id,
                    vector={
                        "": vector,
                        _SPARSE_VECTOR_NAME: sparse,
                    },
                    payload=ChunkPayload(
                        chunk_id=chunk.chunk_id,
                        document_id=chunk.document_id,
                        filename=chunk.filename,
                        page_number=chunk.page_number,
                        chunk_index=chunk.chunk_index,
                        text=chunk.text,
                    ).model_dump(),
                )
                for chunk, vector, sparse in zip(chunks, vectors, sparse_vectors, strict=True)
            ]
        else:
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
                "has_sparse": sparse_vectors is not None,
                "document_id": chunks[0].document_id if chunks else None,
            },
        )

    def search(
        self,
        vector: list[float],
        top_k: int,
        score_threshold: float,
        document_id_filter: str | list[str] | None = None,
    ) -> list[RetrievedChunk]:
        """
        Dense vector search with cosine similarity.

        Args:
            vector: Query embedding produced by the embedding model.
            top_k: Maximum number of results to return.
            score_threshold: Minimum cosine similarity for inclusion (server-side).
            document_id_filter: If set, restrict search to chunks from this document.

        Returns:
            List of RetrievedChunk objects sorted by score descending.
        """
        response = self._client.query_points(
            collection_name=self._collection_name,
            query=vector,
            query_filter=self._build_filter(document_id_filter),
            limit=top_k,
            score_threshold=score_threshold,
            with_payload=True,
        )

        chunks = self._points_to_chunks(response.points)

        logger.debug(
            "Qdrant dense search complete",
            extra={
                "collection": self._collection_name,
                "top_k": top_k,
                "score_threshold": score_threshold,
                "results_count": len(chunks),
                "document_id_filter": document_id_filter,
            },
        )

        return chunks

    def hybrid_search(
        self,
        dense_vector: list[float],
        sparse_vector: SparseVector,
        top_k: int,
        score_threshold: float,
        document_id_filter: str | list[str] | None = None,
    ) -> list[RetrievedChunk]:
        """
        Hybrid search: dense vector + BM25 sparse, fused with Reciprocal Rank Fusion.

        Uses Qdrant's native Prefetch + FusionQuery mechanism:
          1. Dense prefetch (cosine) → top_k*2 candidates, filtered by score_threshold
          2. Sparse prefetch (BM25)  → top_k*2 candidates (no score threshold — BM25
             scores are on a different scale than cosine similarity)
          3. RRF fusion ranks both result sets and returns top_k combined results

        Points that only have dense vectors (uploaded before sparse was enabled) will
        appear in the dense prefetch but not the sparse prefetch; RRF handles this
        gracefully by assigning them a rank-based score from the dense list only.

        Args:
            dense_vector: Query embedding from OllamaEmbedder.
            sparse_vector: BM25 query vector from SparseEmbedder.
            top_k: Final number of results after RRF fusion.
            score_threshold: Applied to dense prefetch only.
            document_id_filter: If set, restrict search to chunks from this document.

        Returns:
            List of RetrievedChunk objects sorted by RRF score descending.
        """
        doc_filter = self._build_filter(document_id_filter)

        try:
            response = self._client.query_points(
                collection_name=self._collection_name,
                prefetch=[
                    Prefetch(
                        query=dense_vector,
                        using="",
                        limit=top_k * 2,
                        score_threshold=score_threshold,
                        filter=doc_filter,
                    ),
                    Prefetch(
                        query=sparse_vector,
                        using=_SPARSE_VECTOR_NAME,
                        limit=top_k * 2,
                        filter=doc_filter,
                    ),
                ],
                query=FusionQuery(fusion=Fusion.RRF),
                limit=top_k,
                with_payload=True,
            )
            chunks = self._points_to_chunks(response.points)
        except Exception as exc:
            if "Not existing vector name" in str(exc) or "text-sparse" in str(exc):
                logger.warning(
                    "Hybrid search failed (sparse field missing) — falling back to dense search",
                    extra={"collection": self._collection_name, "error": str(exc)[:120]},
                )
                return self.search(
                    vector=dense_vector,
                    top_k=top_k,
                    score_threshold=score_threshold,
                    document_id_filter=document_id_filter,  # str | list[str] | None
                )
            raise

        logger.debug(
            "Qdrant hybrid search complete",
            extra={
                "collection": self._collection_name,
                "top_k": top_k,
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

    # ── Private helpers ────────────────────────────────────────────────────────

    def _build_filter(self, document_id_filter: str | list[str] | None) -> Filter | None:
        """Return a Qdrant keyword filter for one or more document_ids, or None."""
        if not document_id_filter:
            return None
        if isinstance(document_id_filter, str):
            return Filter(
                must=[FieldCondition(key="document_id", match=MatchValue(value=document_id_filter))]
            )
        if len(document_id_filter) == 1:
            return Filter(
                must=[FieldCondition(key="document_id", match=MatchValue(value=document_id_filter[0]))]
            )
        # OR filter across all member documents in a collection.
        return Filter(
            should=[
                FieldCondition(key="document_id", match=MatchValue(value=did))
                for did in document_id_filter
            ]
        )

    def _points_to_chunks(self, points) -> list[RetrievedChunk]:
        """Convert a list of Qdrant ScoredPoint objects to RetrievedChunk models."""
        return [
            RetrievedChunk(
                chunk_id=r.payload["chunk_id"],
                text=r.payload["text"],
                score=r.score,
                document_id=r.payload["document_id"],
                filename=r.payload["filename"],
                page_number=r.payload["page_number"],
                chunk_index=r.payload["chunk_index"],
            )
            for r in points
        ]

    def _create_collection(self) -> None:
        """Create the collection with dense and sparse vector configurations."""
        self._client.create_collection(
            collection_name=self._collection_name,
            vectors_config=VectorParams(
                size=self._vector_size,
                distance=Distance.COSINE,
            ),
            sparse_vectors_config={
                _SPARSE_VECTOR_NAME: SparseVectorParams()
            },
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
                "sparse_field": _SPARSE_VECTOR_NAME,
            },
        )

    def _ensure_sparse_vector_field(self) -> None:
        """
        Verify the sparse vector field is present; log a warning if not.

        Qdrant 1.18+ does not allow adding sparse vectors to an existing
        collection that was created without them (both gRPC and REST PATCH
        silently ignore or reject the operation). Sparse vectors are included
        in _create_collection() so all newly created collections have them.
        Existing legacy collections show a warning and fall back to dense search.
        """
        info = self._client.get_collection(self._collection_name)
        existing_sparse = info.config.params.sparse_vectors or {}
        if _SPARSE_VECTOR_NAME in existing_sparse:
            logger.debug(
                "Sparse vector field present",
                extra={"collection": self._collection_name, "field": _SPARSE_VECTOR_NAME},
            )
            return

        logger.warning(
            "Sparse vector field missing from existing collection — hybrid search "
            "will fall back to dense-only. Delete and recreate the collection "
            "(re-upload documents) to enable hybrid search.",
            extra={"collection": self._collection_name, "field": _SPARSE_VECTOR_NAME},
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
