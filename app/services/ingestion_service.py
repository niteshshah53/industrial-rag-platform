"""
Document ingestion pipeline orchestrator.

This service owns the entire ingestion lifecycle:
  1. Validate file type (magic bytes) and size
  2. Compute SHA-256 hash and check for duplicates
  3. Persist PENDING DocumentRecord to SQLite
  4. Queue background task to run the full pipeline
  5. Background task: PROCESSING → extract → chunk → embed → upsert → READY
                                                               (or FAILED on error)

Design decisions:
  - Async public API: upload() and get/list/delete are async so they
    integrate naturally with FastAPI route handlers.
  - CPU-bound work in thread pool: pdfplumber parsing, text splitting, and
    Ollama embedding are all synchronous. We wrap the entire sync pipeline in
    asyncio.get_event_loop().run_in_executor(None, ...) to avoid blocking the
    event loop. A semaphore (ingestion_concurrency) caps parallel ingestions
    to prevent OOM from simultaneous large documents.
  - Failure isolation: any exception inside the background task is caught,
    the document is marked FAILED, and the exception is re-logged. Qdrant
    vectors already written are cleaned up to avoid orphans.
  - Pre-task validation happens synchronously in upload() before the DB insert.
    This lets us return 409/422 errors immediately rather than deferring them
    to the background task.

Concurrency model:
  asyncio.Semaphore(ingestion_concurrency) ensures at most N ingestion pipelines
  run simultaneously. Each pipeline is a single run_in_executor call executing
  the entire sync pipeline on a thread pool thread.
"""

import asyncio
import hashlib
import uuid
from datetime import UTC, datetime
from functools import partial

from app.core.config import Settings
from app.core.exceptions import (
    DocumentAlreadyExistsError,
    DocumentNotFoundError,
    FileTooLargeError,
)
from app.core.logging import get_logger
from app.core.models import DocumentListResponse, DocumentRecord, DocumentStatus, UploadResponse
from app.db.document_repository import DocumentRepository
from app.db.qdrant_repository import QdrantRepository
from app.rag.chunker import DocumentChunker
from app.rag.embedder import OllamaEmbedder
from app.rag.extractor import get_extractor

logger = get_logger(__name__)


class IngestionService:
    """
    Orchestrates document upload validation and background ingestion.

    Args:
        settings: Application settings (model names, limits, concurrency).
        doc_repo: SQLite document registry.
        qdrant_repo: Qdrant vector store repository.
    """

    def __init__(
        self,
        settings: Settings,
        doc_repo: DocumentRepository,
        qdrant_repo: QdrantRepository,
    ) -> None:
        self._settings = settings
        self._doc_repo = doc_repo
        self._qdrant_repo = qdrant_repo
        self._semaphore = asyncio.Semaphore(settings.ingestion_concurrency)

    # ── Public API ─────────────────────────────────────────────────────────────

    async def upload(self, filename: str, content: bytes) -> UploadResponse:
        """
        Validate the upload, persist a PENDING record, and return immediately.

        The heavy ingestion work (extraction → chunking → embedding → upsert)
        is NOT run here. The caller (route handler) must pass
        `self.run_ingestion(document_id, content)` to FastAPI BackgroundTasks.

        Args:
            filename: Original filename from the multipart upload.
            content: Raw file bytes.

        Returns:
            UploadResponse with the new document_id and PENDING status.

        Raises:
            FileTooLargeError: File exceeds max_upload_size_mb.
            InvalidFileTypeError: File format is not supported (PDF/DOCX/TXT).
            DocumentAlreadyExistsError: A document with the same content already exists.
        """
        # 1. Size check
        max_bytes = self._settings.max_upload_size_mb * 1024 * 1024
        if len(content) > max_bytes:
            raise FileTooLargeError(
                filename=filename,
                size_mb=len(content) / (1024 * 1024),
                max_mb=self._settings.max_upload_size_mb,
            )

        # 2. Format detection — raises InvalidFileTypeError for unsupported types
        get_extractor(content, filename)

        # 3. SHA-256 deduplication — only block if a non-failed record exists.
        # A FAILED document has no vectors in Qdrant, so re-uploading it is safe.
        file_hash = "sha256:" + hashlib.sha256(content).hexdigest()
        existing = self._doc_repo.get_by_hash(file_hash)
        if existing is not None and existing.status != DocumentStatus.FAILED:
            raise DocumentAlreadyExistsError(
                document_id=existing.document_id,
                filename=existing.filename,
            )
        if existing is not None and existing.status == DocumentStatus.FAILED:
            # Delete the stale failed record so a fresh one can be created.
            self._doc_repo.delete(existing.document_id)

        # 4. Persist PENDING record
        document_id = str(uuid.uuid4())
        record = DocumentRecord(
            document_id=document_id,
            filename=filename,
            file_hash=file_hash,
            status=DocumentStatus.PENDING,
            chunk_count=0,
            upload_timestamp=datetime.now(UTC),
            file_size_bytes=len(content),
        )
        self._doc_repo.insert(record)

        logger.info(
            "Document accepted for ingestion",
            extra={"document_id": document_id, "doc_filename": filename},
        )

        return UploadResponse(
            document_id=document_id,
            filename=filename,
            status=DocumentStatus.PENDING,
            message="File accepted. Ingestion running in background.",
        )

    async def run_ingestion(self, document_id: str, content: bytes) -> None:
        """
        Run the full ingestion pipeline in a background thread.

        Designed to be passed directly to FastAPI BackgroundTasks:
            background_tasks.add_task(service.run_ingestion, doc_id, content)

        Acquires the concurrency semaphore before starting. The entire
        sync pipeline runs in a single run_in_executor call to avoid
        blocking the asyncio event loop.

        Args:
            document_id: UUID of the already-persisted PENDING document.
            content: Raw PDF bytes to ingest.
        """
        async with self._semaphore:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                partial(self._run_ingestion_sync, document_id, content),
            )

    def get_document(self, document_id: str) -> DocumentRecord:
        """
        Return a single DocumentRecord by ID.

        Raises:
            DocumentNotFoundError: No document with this ID exists.
        """
        record = self._doc_repo.get_by_id(document_id)
        if record is None:
            raise DocumentNotFoundError(document_id)
        return record

    def list_documents(self) -> DocumentListResponse:
        """Return all documents in the registry."""
        documents = self._doc_repo.list_all()
        return DocumentListResponse(documents=documents, total=len(documents))

    async def delete_document(self, document_id: str) -> None:
        """
        Delete a document from SQLite and remove its vectors from Qdrant.

        Args:
            document_id: UUID of the document to delete.

        Raises:
            DocumentNotFoundError: No document with this ID exists.
        """
        record = self._doc_repo.get_by_id(document_id)
        if record is None:
            raise DocumentNotFoundError(document_id)

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, partial(self._qdrant_repo.delete_document, document_id))
        self._doc_repo.delete(document_id)

        logger.info("Document deleted", extra={"document_id": document_id})

    # ── Private sync pipeline ──────────────────────────────────────────────────

    def _run_ingestion_sync(self, document_id: str, content: bytes) -> None:
        """
        Synchronous ingestion pipeline — runs in a thread pool.

        Steps:
          1. Mark document PROCESSING
          2. Extract text pages with pdfplumber
          3. Chunk with RecursiveCharacterTextSplitter
          4. Embed with Ollama
          5. Upsert to Qdrant
          6. Mark document READY with chunk count
          On any error: mark FAILED, attempt Qdrant cleanup, re-log.
        """
        logger.info("Ingestion pipeline started", extra={"document_id": document_id})

        try:
            self._doc_repo.update_status(document_id, DocumentStatus.PROCESSING)

            # Step 1: Extract — pick the right extractor from content + filename
            record = self._doc_repo.get_by_id(document_id)
            filename = record.filename if record else "unknown"
            extractor = get_extractor(content, filename)
            pages = extractor.extract(content, filename)

            # Step 2: Chunk
            chunker = DocumentChunker(
                chunk_size_chars=self._settings.chunk_size_chars,
                chunk_overlap_chars=self._settings.chunk_overlap_chars,
            )
            chunks = chunker.chunk(pages=pages, document_id=document_id, filename=filename)

            if not chunks:
                raise ValueError("Chunker produced zero chunks — document may be empty.")

            # Step 3: Embed
            embedder = OllamaEmbedder(
                base_url=self._settings.ollama_base_url,
                model=self._settings.embedding_model,
                batch_size=self._settings.embedding_batch_size,
            )
            chunk_vector_pairs = embedder.embed(chunks)
            embedded_chunks = [c for c, _ in chunk_vector_pairs]
            vectors = [v for _, v in chunk_vector_pairs]

            # Step 4: Upsert to Qdrant
            self._qdrant_repo.upsert_chunks(embedded_chunks, vectors)

            # Step 5: Mark READY
            self._doc_repo.update_status(
                document_id,
                DocumentStatus.READY,
                chunk_count=len(chunks),
            )

            logger.info(
                "Ingestion pipeline complete",
                extra={"document_id": document_id, "chunk_count": len(chunks)},
            )

        except Exception as exc:
            error_message = f"{type(exc).__name__}: {exc}"
            logger.error(
                "Ingestion pipeline failed",
                extra={"document_id": document_id, "error": error_message},
                exc_info=exc,
            )
            # Attempt to clean up any partial Qdrant writes.
            try:
                self._qdrant_repo.delete_document(document_id)
            except Exception as cleanup_exc:
                logger.warning(
                    "Failed to clean up Qdrant after ingestion failure",
                    extra={"document_id": document_id, "cleanup_error": str(cleanup_exc)},
                )

            self._doc_repo.update_status(
                document_id,
                DocumentStatus.FAILED,
                error_message=error_message,
            )
