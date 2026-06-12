"""
Shared domain models for the Industrial RAG Platform.

These Pydantic models represent the core data structures that flow
between layers. They are defined here (Core Layer) so that all layers
can import them without creating circular dependencies.

Models are added per phase:
  Phase 0 (this file): DocumentStatus, DocumentRecord
  Phase 1:             DocumentChunk, ChunkPayload, UploadResponse, DocumentListResponse
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


# ── Phase 1 ───────────────────────────────────────────────────────────────────


class DocumentChunk(BaseModel):
    """
    A single text chunk produced by the chunker, before embedding.

    Created by DocumentChunker and passed to OllamaEmbedder.
    The chunk_id is a deterministic UUID derived from document_id + chunk_index,
    ensuring idempotent re-ingestion.
    """

    chunk_id: str = Field(
        description="Deterministic UUID: str(uuid.UUID(hex=sha256(f'{document_id}:{chunk_index}')[:32]))"
    )
    document_id: str = Field(description="Parent document UUID")
    filename: str = Field(description="Original filename, included for Qdrant payload")
    text: str = Field(description="Raw chunk text content")
    page_number: int = Field(description="1-indexed page number the chunk originates from")
    chunk_index: int = Field(description="0-indexed position of this chunk within the document")
    char_count: int = Field(description="Character count of the text field")


class ChunkPayload(BaseModel):
    """
    Payload stored alongside each vector point in Qdrant.

    All fields must be JSON-serialisable. The payload is retrieved at
    query time and used to construct citations without a separate DB lookup.
    """

    chunk_id: str = Field(description="Matches DocumentChunk.chunk_id")
    document_id: str = Field(description="Parent document UUID — indexed as KEYWORD in Qdrant")
    filename: str = Field(description="Original filename for citation display")
    page_number: int = Field(description="1-indexed page number for citation")
    chunk_index: int = Field(description="0-indexed chunk position within the document")
    text: str = Field(description="Chunk text, returned alongside the score at retrieval time")


class UploadResponse(BaseModel):
    """
    Response body for POST /v1/documents/upload.

    Returns immediately after file validation passes and the background
    ingestion task is queued. The client must poll GET /v1/documents/{id}
    to determine when status transitions to READY or FAILED.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "document_id": "a3f2b1c0-1234-5678-abcd-ef0123456789",
                "filename": "maintenance_manual.pdf",
                "status": "PENDING",
                "message": "File accepted. Ingestion running in background.",
            }
        }
    )

    document_id: str = Field(description="UUID assigned to this document")
    filename: str = Field(description="Original filename as uploaded")
    status: DocumentStatus = Field(description="Always PENDING at upload time")
    message: str = Field(description="Human-readable confirmation message")


class DocumentListResponse(BaseModel):
    """Response body for GET /v1/documents."""

    documents: list[DocumentRecord] = Field(description="All documents in the registry")
    total: int = Field(description="Total number of documents")


# ── Phase 2 ───────────────────────────────────────────────────────────────────


class RetrievedChunk(BaseModel):
    """
    A single chunk returned by Qdrant vector search with its similarity score.

    Score is stored on the chunk object — there is no parallel score list.
    This prevents coherence bugs if chunks are reordered or filtered downstream.
    """

    chunk_id: str = Field(description="Matches the chunk_id stored in Qdrant payload")
    text: str = Field(description="Chunk text content")
    score: float = Field(description="Cosine similarity score from Qdrant [0, 1]")
    document_id: str = Field(description="Parent document UUID")
    filename: str = Field(description="Original filename for citation display")
    page_number: int = Field(description="1-indexed page number the chunk originates from")
    chunk_index: int = Field(description="0-indexed position within the document")


class Citation(BaseModel):
    """
    A source citation included in a query response.

    Built by the cite step from RetrievedChunk metadata.
    Provides the information a user needs to locate the source passage.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "document_name": "maintenance_manual.pdf",
                "page_number": 7,
                "chunk_index": 12,
                "relevance_score": 0.84,
            }
        }
    )

    document_name: str = Field(description="Original filename of the source document")
    page_number: int = Field(description="Page the cited passage appears on (1-indexed)")
    chunk_index: int = Field(description="Position of the chunk within the document")
    relevance_score: float = Field(description="Cosine similarity score of this chunk [0, 1]")


class QueryRequest(BaseModel):
    """Request body for POST /v1/chat/query."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "question": "What is the maximum operating temperature of the hydraulic system?",
                "top_k": 5,
                "score_threshold": 0.6,
                "document_id": None,
                "include_contexts": False,
            }
        }
    )

    question: str = Field(
        min_length=1,
        max_length=1000,
        description="Natural-language question to answer using the document corpus",
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum number of chunks to retrieve from Qdrant",
    )
    score_threshold: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        description="Minimum cosine similarity score for a chunk to be included",
    )
    document_id: str | None = Field(
        default=None,
        description="Optional: restrict retrieval to chunks from this document only",
    )
    include_contexts: bool = Field(
        default=False,
        description=(
            "When True, the response includes the raw context strings passed to the LLM. "
            "Used by the evaluation pipeline to populate RAGAS retrieved_contexts. "
            "Defaults to False to keep production responses compact."
        ),
    )


class QueryResponse(BaseModel):
    """Response body for POST /v1/chat/query."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "answer": "The maximum operating temperature of the hydraulic system is 85°C, as specified in Section 4.2.",
                "citations": [
                    {
                        "document_name": "maintenance_manual.pdf",
                        "page_number": 7,
                        "chunk_index": 12,
                        "relevance_score": 0.84,
                    }
                ],
                "retrieval_count": 5,
                "context_chunks_used": 3,
                "latency_ms": 1240.5,
                "request_id": "a3f2b1c0-1234-5678-abcd-ef0123456789",
            }
        }
    )

    answer: str = Field(description="Generated answer grounded in retrieved context")
    citations: list[Citation] = Field(
        description="Source citations from the retrieved chunks used to generate the answer"
    )
    retrieval_count: int = Field(
        description="Total chunks returned by Qdrant before budget enforcement"
    )
    context_chunks_used: int = Field(
        description="Chunks actually included in the LLM context after budget enforcement"
    )
    latency_ms: float = Field(description="Total end-to-end query latency in milliseconds")
    request_id: str = Field(description="Correlation ID for tracing this request in logs")
    contexts: list[str] | None = Field(
        default=None,
        description=(
            "Raw context strings passed to the LLM, one per included chunk. "
            "Only present when QueryRequest.include_contexts=True. "
            "Used by the RAGAS evaluation pipeline."
        ),
    )
