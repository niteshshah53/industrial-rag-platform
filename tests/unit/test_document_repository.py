"""
Unit tests for DocumentRepository.

Uses an in-memory SQLite database (:memory:) for full isolation.
No Docker or filesystem side effects.
"""

from datetime import UTC, datetime

import pytest

from app.core.models import DocumentRecord, DocumentStatus
from app.db.document_repository import DocumentRepository

# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture
def repo(tmp_path) -> DocumentRepository:
    """DocumentRepository backed by a temp-dir SQLite file, reset per test."""
    db_file = tmp_path / "test_documents.db"
    r = DocumentRepository(db_path=str(db_file))
    r.create_tables()
    return r


def _make_record(
    document_id: str = "doc-001",
    filename: str = "manual.pdf",
    file_hash: str = "sha256:abc123",
    status: DocumentStatus = DocumentStatus.PENDING,
) -> DocumentRecord:
    return DocumentRecord(
        document_id=document_id,
        filename=filename,
        file_hash=file_hash,
        status=status,
        chunk_count=0,
        upload_timestamp=datetime.now(UTC),
        file_size_bytes=1024,
    )


# ── Tests ──────────────────────────────────────────────────────────────────────


class TestDocumentRepositoryInsertAndGet:
    def test_insert_and_get_by_id(self, repo):
        record = _make_record()
        repo.insert(record)
        retrieved = repo.get_by_id("doc-001")
        assert retrieved is not None
        assert retrieved.document_id == "doc-001"
        assert retrieved.filename == "manual.pdf"

    def test_get_by_id_returns_none_for_missing(self, repo):
        assert repo.get_by_id("nonexistent") is None

    def test_get_by_hash_finds_existing(self, repo):
        record = _make_record(file_hash="sha256:unique_hash")
        repo.insert(record)
        retrieved = repo.get_by_hash("sha256:unique_hash")
        assert retrieved is not None
        assert retrieved.document_id == "doc-001"

    def test_get_by_hash_returns_none_for_missing(self, repo):
        assert repo.get_by_hash("sha256:nonexistent") is None

    def test_status_is_preserved(self, repo):
        record = _make_record(status=DocumentStatus.READY)
        repo.insert(record)
        retrieved = repo.get_by_id("doc-001")
        assert retrieved.status == DocumentStatus.READY


class TestDocumentRepositoryListAll:
    def test_list_all_returns_empty_initially(self, repo):
        assert repo.list_all() == []

    def test_list_all_returns_all_records(self, repo):
        repo.insert(_make_record("doc-001", file_hash="sha256:h1"))
        repo.insert(_make_record("doc-002", file_hash="sha256:h2"))
        repo.insert(_make_record("doc-003", file_hash="sha256:h3"))
        records = repo.list_all()
        assert len(records) == 3

    def test_list_all_returns_document_record_instances(self, repo):
        repo.insert(_make_record())
        records = repo.list_all()
        assert all(isinstance(r, DocumentRecord) for r in records)


class TestDocumentRepositoryUpdateStatus:
    def test_update_to_processing(self, repo):
        repo.insert(_make_record())
        repo.update_status("doc-001", DocumentStatus.PROCESSING)
        record = repo.get_by_id("doc-001")
        assert record.status == DocumentStatus.PROCESSING

    def test_update_to_ready_with_chunk_count(self, repo):
        repo.insert(_make_record())
        repo.update_status("doc-001", DocumentStatus.READY, chunk_count=42)
        record = repo.get_by_id("doc-001")
        assert record.status == DocumentStatus.READY
        assert record.chunk_count == 42

    def test_update_to_failed_with_error_message(self, repo):
        repo.insert(_make_record())
        repo.update_status(
            "doc-001", DocumentStatus.FAILED, error_message="Extraction failed: no text layer"
        )
        record = repo.get_by_id("doc-001")
        assert record.status == DocumentStatus.FAILED
        assert "Extraction failed" in record.error_message

    def test_update_nonexistent_document_does_not_raise(self, repo):
        # Should log a warning and return gracefully
        repo.update_status("ghost-id", DocumentStatus.FAILED)  # no exception

    def test_chunk_count_defaults_zero_on_insert(self, repo):
        repo.insert(_make_record())
        record = repo.get_by_id("doc-001")
        assert record.chunk_count == 0


class TestDocumentRepositoryDelete:
    def test_delete_existing_returns_true(self, repo):
        repo.insert(_make_record())
        assert repo.delete("doc-001") is True
        assert repo.get_by_id("doc-001") is None

    def test_delete_nonexistent_returns_false(self, repo):
        assert repo.delete("does-not-exist") is False

    def test_list_all_excludes_deleted(self, repo):
        repo.insert(_make_record("doc-001", file_hash="sha256:h1"))
        repo.insert(_make_record("doc-002", file_hash="sha256:h2"))
        repo.delete("doc-001")
        records = repo.list_all()
        assert len(records) == 1
        assert records[0].document_id == "doc-002"


class TestDocumentRepositoryIsolation:
    def test_separate_instances_share_same_file(self, tmp_path):
        """Two repository instances pointing at the same file should share state."""
        db_path = str(tmp_path / "shared.db")
        repo1 = DocumentRepository(db_path=db_path)
        repo1.create_tables()
        repo1.insert(_make_record())

        repo2 = DocumentRepository(db_path=db_path)
        record = repo2.get_by_id("doc-001")
        assert record is not None
        assert record.filename == "manual.pdf"
