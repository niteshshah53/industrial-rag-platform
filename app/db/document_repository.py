"""
SQLite document registry via SQLModel.

Responsibilities:
  - Persist DocumentRecord metadata (not vectors — those live in Qdrant)
  - Create the database schema on first startup
  - CRUD operations: insert, get by id, get by hash, list, update, delete
  - Thread-safe for concurrent BackgroundTask writes

Design decisions:
  - SQLModel chosen over raw SQLAlchemy for its Pydantic-first API that
    aligns with the rest of the codebase.
  - DocumentRow (SQLModel table=True) is separated from DocumentRecord
    (Pydantic BaseModel) to maintain Clean Architecture — the DB schema
    is an implementation detail, not a domain concern. Conversion helpers
    handle translation between the two.
  - check_same_thread=False: FastAPI BackgroundTasks run on a thread pool,
    so the default SQLite restriction must be lifted. SQLModel+SQLAlchemy
    manages connection state per-thread safely.
  - A single shared engine instance (module-level) is created once and
    reused across all requests for connection pooling efficiency.
"""

import uuid
from datetime import UTC, datetime

from sqlmodel import Field, Session, SQLModel, create_engine, select

from app.core.logging import get_logger
from app.core.models import CollectionRecord, DocumentRecord, DocumentStatus

logger = get_logger(__name__)


# ── SQLModel Table ─────────────────────────────────────────────────────────────


class DocumentRow(SQLModel, table=True):
    """
    SQLite table row for a document record.

    Intentionally mirrors DocumentRecord but uses SQLModel so it can be
    persisted. Keep field names in sync with DocumentRecord; if they diverge,
    update the _to_record / _from_record helpers below.
    """

    __tablename__ = "documents"

    document_id: str = Field(primary_key=True)
    filename: str
    file_hash: str = Field(index=True)  # Indexed for O(1) duplicate detection
    status: str  # Stored as string; use DocumentStatus enum at the service layer
    chunk_count: int = Field(default=0)
    upload_timestamp: datetime
    file_size_bytes: int
    error_message: str | None = Field(default=None)


# ── Collection SQLModel Tables ─────────────────────────────────────────────────


class CollectionRow(SQLModel, table=True):
    """SQLite table row for a named document collection."""

    __tablename__ = "collections"

    collection_id: str = Field(primary_key=True)
    name: str = Field(index=True)
    description: str | None = Field(default=None)
    created_at: datetime


class CollectionMemberRow(SQLModel, table=True):
    """Join table: maps collection_id → document_id (many-to-many)."""

    __tablename__ = "collection_members"

    collection_id: str = Field(primary_key=True)
    document_id: str = Field(primary_key=True)


# ── Repository ─────────────────────────────────────────────────────────────────


class DocumentRepository:
    """
    Data access object for the SQLite document registry.

    Args:
        db_path: Filesystem path to the SQLite database file.
                 Defaults to "documents.db" in the current directory.
    """

    def __init__(self, db_path: str = "documents.db") -> None:
        self._engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
        )

    def create_tables(self) -> None:
        """Create all SQLModel tables. Safe to call multiple times (CREATE IF NOT EXISTS)."""
        SQLModel.metadata.create_all(self._engine)
        logger.info("Document registry tables created", extra={"db_path": str(self._engine.url)})

    # ── Write ──────────────────────────────────────────────────────────────────

    def insert(self, record: DocumentRecord) -> None:
        """
        Insert a new document record.

        Args:
            record: DocumentRecord to persist.
        """
        row = self._from_record(record)
        with Session(self._engine) as session:
            session.add(row)
            session.commit()
        logger.debug(
            "Document inserted",
            extra={"document_id": record.document_id, "doc_filename": record.filename},
        )

    def update_status(
        self,
        document_id: str,
        status: DocumentStatus,
        chunk_count: int | None = None,
        error_message: str | None = None,
    ) -> None:
        """
        Update the status (and optionally chunk_count/error_message) of a document.

        Args:
            document_id: UUID of the document to update.
            status: New DocumentStatus value.
            chunk_count: Number of chunks stored in Qdrant (set when READY).
            error_message: Human-readable error description (set when FAILED).
        """
        with Session(self._engine) as session:
            row = session.get(DocumentRow, document_id)
            if row is None:
                logger.warning(
                    "update_status called on missing document",
                    extra={"document_id": document_id},
                )
                return
            row.status = status.value
            if chunk_count is not None:
                row.chunk_count = chunk_count
            if error_message is not None:
                row.error_message = error_message
            session.add(row)
            session.commit()

        logger.debug(
            "Document status updated",
            extra={"document_id": document_id, "status": status},
        )

    def delete(self, document_id: str) -> bool:
        """
        Delete a document record by ID.

        Returns:
            True if a record was deleted, False if none was found.
        """
        with Session(self._engine) as session:
            row = session.get(DocumentRow, document_id)
            if row is None:
                return False
            session.delete(row)
            session.commit()

        logger.debug("Document deleted", extra={"document_id": document_id})
        return True

    # ── Read ───────────────────────────────────────────────────────────────────

    def get_by_id(self, document_id: str) -> DocumentRecord | None:
        """Return the DocumentRecord for the given ID, or None if not found."""
        with Session(self._engine) as session:
            row = session.get(DocumentRow, document_id)
            return self._to_record(row) if row else None

    def get_by_hash(self, file_hash: str) -> DocumentRecord | None:
        """
        Return the DocumentRecord for the given file hash, or None.

        Used for duplicate detection at upload time.
        """
        with Session(self._engine) as session:
            statement = select(DocumentRow).where(DocumentRow.file_hash == file_hash)
            row = session.exec(statement).first()
            return self._to_record(row) if row else None

    def list_all(self) -> list[DocumentRecord]:
        """Return all document records, ordered by upload_timestamp descending."""
        with Session(self._engine) as session:
            statement = select(DocumentRow).order_by(DocumentRow.upload_timestamp.desc())  # type: ignore[attr-defined]
            rows = session.exec(statement).all()
            return [self._to_record(row) for row in rows]

    # ── Helpers ────────────────────────────────────────────────────────────────

    # ── Collection CRUD ────────────────────────────────────────────────────────

    def create_collection(
        self,
        name: str,
        description: str | None = None,
        document_ids: list[str] | None = None,
    ) -> CollectionRecord:
        """Create a new collection and optionally add initial members."""
        collection_id = str(uuid.uuid4())
        now = utcnow()
        row = CollectionRow(
            collection_id=collection_id,
            name=name,
            description=description,
            created_at=now,
        )
        with Session(self._engine) as session:
            session.add(row)
            for doc_id in (document_ids or []):
                session.add(CollectionMemberRow(collection_id=collection_id, document_id=doc_id))
            session.commit()

        logger.debug("Collection created", extra={"collection_id": collection_id, "name": name})
        return CollectionRecord(
            collection_id=collection_id,
            name=name,
            description=description,
            document_ids=list(document_ids or []),
            created_at=now,
        )

    def get_collection(self, collection_id: str) -> CollectionRecord | None:
        """Return a CollectionRecord with its member document_ids, or None."""
        with Session(self._engine) as session:
            row = session.get(CollectionRow, collection_id)
            if row is None:
                return None
            members = session.exec(
                select(CollectionMemberRow).where(CollectionMemberRow.collection_id == collection_id)
            ).all()
            return CollectionRecord(
                collection_id=row.collection_id,
                name=row.name,
                description=row.description,
                document_ids=[m.document_id for m in members],
                created_at=row.created_at,
            )

    def list_collections(self) -> list[CollectionRecord]:
        """Return all collections with their member document_ids, newest first."""
        with Session(self._engine) as session:
            rows = session.exec(
                select(CollectionRow).order_by(CollectionRow.created_at.desc())  # type: ignore[attr-defined]
            ).all()
            result = []
            for row in rows:
                members = session.exec(
                    select(CollectionMemberRow).where(
                        CollectionMemberRow.collection_id == row.collection_id
                    )
                ).all()
                result.append(
                    CollectionRecord(
                        collection_id=row.collection_id,
                        name=row.name,
                        description=row.description,
                        document_ids=[m.document_id for m in members],
                        created_at=row.created_at,
                    )
                )
            return result

    def delete_collection(self, collection_id: str) -> bool:
        """Delete a collection and all its membership entries. Returns False if not found."""
        with Session(self._engine) as session:
            row = session.get(CollectionRow, collection_id)
            if row is None:
                return False
            members = session.exec(
                select(CollectionMemberRow).where(CollectionMemberRow.collection_id == collection_id)
            ).all()
            for m in members:
                session.delete(m)
            session.delete(row)
            session.commit()
        logger.debug("Collection deleted", extra={"collection_id": collection_id})
        return True

    def add_document_to_collection(self, collection_id: str, document_id: str) -> bool:
        """Add a document to a collection. Returns False if already a member."""
        with Session(self._engine) as session:
            existing = session.get(CollectionMemberRow, (collection_id, document_id))
            if existing is not None:
                return False
            session.add(CollectionMemberRow(collection_id=collection_id, document_id=document_id))
            session.commit()
        return True

    def remove_document_from_collection(self, collection_id: str, document_id: str) -> bool:
        """Remove a document from a collection. Returns False if not a member."""
        with Session(self._engine) as session:
            row = session.get(CollectionMemberRow, (collection_id, document_id))
            if row is None:
                return False
            session.delete(row)
            session.commit()
        return True

    def get_collection_document_ids(self, collection_id: str) -> list[str]:
        """Return all document_ids belonging to a collection."""
        with Session(self._engine) as session:
            members = session.exec(
                select(CollectionMemberRow).where(CollectionMemberRow.collection_id == collection_id)
            ).all()
            return [m.document_id for m in members]

    def remove_document_from_all_collections(self, document_id: str) -> None:
        """Remove a document from every collection it belongs to (called on document delete)."""
        with Session(self._engine) as session:
            rows = session.exec(
                select(CollectionMemberRow).where(CollectionMemberRow.document_id == document_id)
            ).all()
            for row in rows:
                session.delete(row)
            session.commit()

    @staticmethod
    def _to_record(row: DocumentRow) -> DocumentRecord:
        """Convert a DocumentRow ORM object to a DocumentRecord Pydantic model."""
        return DocumentRecord(
            document_id=row.document_id,
            filename=row.filename,
            file_hash=row.file_hash,
            status=DocumentStatus(row.status),
            chunk_count=row.chunk_count,
            upload_timestamp=row.upload_timestamp,
            file_size_bytes=row.file_size_bytes,
            error_message=row.error_message,
        )

    @staticmethod
    def _from_record(record: DocumentRecord) -> DocumentRow:
        """Convert a DocumentRecord Pydantic model to a DocumentRow ORM object."""
        return DocumentRow(
            document_id=record.document_id,
            filename=record.filename,
            file_hash=record.file_hash,
            status=record.status.value,
            chunk_count=record.chunk_count,
            upload_timestamp=record.upload_timestamp,
            file_size_bytes=record.file_size_bytes,
            error_message=record.error_message,
        )


# ── Convenience ────────────────────────────────────────────────────────────────


def utcnow() -> datetime:
    """Return the current UTC datetime (timezone-aware)."""
    return datetime.now(UTC)
