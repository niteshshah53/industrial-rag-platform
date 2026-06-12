"""
Shared domain models for the Industrial RAG Platform.

These Pydantic models represent the core data structures that flow
between layers. They are defined here (Core Layer) so that all layers
can import them without creating circular dependencies.

Models are added per phase:
  Phase 0 (this file): DocumentStatus, DocumentRecord
  Phase 1:             DocumentChunk, ChunkPayload
  Phase 2:             RetrievedChunk, Citation, QueryRequest, QueryResponse
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

# ── Phase 0 ───────────────────────────────────────────────────────────────────


class DocumentStatus(StrEnum):
    """
    Lifecycle states for a document in the ingestion pipeline.

    Transitions:
        PENDING → PROCESSING → READY
                            → FAILED
    """

    PENDING = "PENDING"  # Uploaded, awaiting processing
    PROCESSING = "PROCESSING"  # Actively being ingested
    READY = "READY"  # Fully ingested; vectors in Qdrant
    FAILED = "FAILED"  # Ingestion failed; see error_message


class DocumentRecord(BaseModel):
    """
    Metadata record for an uploaded document.

    Persisted in the SQLite document registry. One record per document.
    Does not contain chunk or vector data — those live in Qdrant.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "document_id": "a3f2b1c0-1234-5678-abcd-ef0123456789",
                "filename": "maintenance_manual.pdf",
                "file_hash": "sha256:abc123...",
                "status": "READY",
                "chunk_count": 42,
                "upload_timestamp": "2026-06-12T14:32:01Z",
                "file_size_bytes": 2097152,
                "error_message": None,
            }
        }
    )

    document_id: str = Field(description="UUID assigned at upload time")
    filename: str = Field(description="Original filename as uploaded by the client")
    file_hash: str = Field(
        description="SHA-256 hex digest of the file content, used for duplicate detection"
    )
    status: DocumentStatus = Field(description="Current processing status")
    chunk_count: int = Field(
        default=0, description="Number of chunks stored in Qdrant; 0 until READY"
    )
    upload_timestamp: datetime = Field(description="UTC timestamp when the file was received")
    file_size_bytes: int = Field(description="Raw file size in bytes")
    error_message: str | None = Field(
        default=None,
        description="Human-readable error description when status is FAILED",
    )


# ── Phase 1 (added during Phase 1 implementation) ─────────────────────────────
#
# class DocumentChunk(BaseModel):
#     """A single text chunk produced by the chunker, before embedding."""
#     chunk_id: str          # sha256(document_id + ":" + chunk_index)[:16]
#     document_id: str
#     text: str
#     page_number: int
#     chunk_index: int
#     char_count: int
#
# class ChunkPayload(BaseModel):
#     """Payload stored alongside each vector in Qdrant."""
#     chunk_id: str
#     document_id: str
#     filename: str
#     page_number: int
#     chunk_index: int
#     text: str


# ── Phase 2 (added during Phase 2 implementation) ─────────────────────────────
#
# class RetrievedChunk(BaseModel):
#     """A chunk returned by Qdrant search, with its similarity score."""
#     chunk_id: str
#     text: str
#     score: float           # Cosine similarity [0, 1]
#     document_id: str
#     filename: str
#     page_number: int
#     chunk_index: int
#
# class Citation(BaseModel):
#     """A source citation included in a query response."""
#     document_name: str
#     page_number: int
#     chunk_index: int
#     relevance_score: float
#
# class QueryRequest(BaseModel):
#     """Request body for POST /v1/chat/query."""
#     question: str
#     top_k: int = 5
#     score_threshold: float = 0.6
#     document_id: str | None = None
#
# class QueryResponse(BaseModel):
#     """Response body for POST /v1/chat/query."""
#     answer: str
#     citations: list[Citation]
#     retrieval_count: int
#     context_chunks_used: int
#     latency_ms: float
#     request_id: str
