"""
Unit tests for the exception hierarchy.

Verifies that each exception:
  - Carries the correct ErrorCode
  - Maps to the correct HTTP status code
  - Includes a human-readable message with the relevant identifiers
"""

from app.core.exceptions import (
    CollectionDimensionMismatchError,
    DocumentAlreadyExistsError,
    DocumentNotFoundError,
    ErrorCode,
    FileTooLargeError,
    InvalidFileTypeError,
    NoTextLayerError,
    PasswordProtectedError,
    ServiceUnavailableError,
)


class TestDocumentNotFoundError:
    def test_status_code(self):
        exc = DocumentNotFoundError("abc123")
        assert exc.status_code == 404

    def test_error_code(self):
        exc = DocumentNotFoundError("abc123")
        assert exc.code == ErrorCode.DOCUMENT_NOT_FOUND

    def test_message_contains_document_id(self):
        exc = DocumentNotFoundError("abc123")
        assert "abc123" in exc.message

    def test_document_id_attribute(self):
        exc = DocumentNotFoundError("abc123")
        assert exc.document_id == "abc123"


class TestDocumentAlreadyExistsError:
    def test_status_code(self):
        exc = DocumentAlreadyExistsError("abc", "manual.pdf")
        assert exc.status_code == 409

    def test_error_code(self):
        exc = DocumentAlreadyExistsError("abc", "manual.pdf")
        assert exc.code == ErrorCode.DOCUMENT_ALREADY_EXISTS

    def test_message_contains_document_id_and_filename(self):
        exc = DocumentAlreadyExistsError("abc", "manual.pdf")
        assert "abc" in exc.message
        assert "manual.pdf" in exc.message


class TestFileValidationErrors:
    def test_invalid_file_type_status_422(self):
        exc = InvalidFileTypeError("evil.exe")
        assert exc.status_code == 422

    def test_invalid_file_type_message(self):
        exc = InvalidFileTypeError("evil.exe")
        assert "evil.exe" in exc.message

    def test_file_too_large_status_422(self):
        exc = FileTooLargeError("big.pdf", size_mb=75.3, max_mb=50)
        assert exc.status_code == 422

    def test_file_too_large_message_contains_sizes(self):
        exc = FileTooLargeError("big.pdf", size_mb=75.3, max_mb=50)
        assert "75.3" in exc.message
        assert "50" in exc.message


class TestIngestionErrors:
    def test_password_protected_status_422(self):
        exc = PasswordProtectedError("locked.pdf")
        assert exc.status_code == 422

    def test_password_protected_message(self):
        exc = PasswordProtectedError("locked.pdf")
        assert "locked.pdf" in exc.message
        assert exc.code == ErrorCode.PASSWORD_PROTECTED

    def test_no_text_layer_status_422(self):
        exc = NoTextLayerError("scan.pdf")
        assert exc.status_code == 422

    def test_no_text_layer_message(self):
        exc = NoTextLayerError("scan.pdf")
        assert "scan.pdf" in exc.message
        assert exc.code == ErrorCode.NO_TEXT_LAYER


class TestInfrastructureErrors:
    def test_service_unavailable_status_503(self):
        exc = ServiceUnavailableError("ollama")
        assert exc.status_code == 503

    def test_service_unavailable_message_contains_service_name(self):
        exc = ServiceUnavailableError("qdrant")
        assert "qdrant" in exc.message

    def test_service_unavailable_with_detail(self):
        exc = ServiceUnavailableError("ollama", detail="Connection refused")
        assert "Connection refused" in exc.message

    def test_collection_dimension_mismatch_status_500(self):
        exc = CollectionDimensionMismatchError("docs", existing_dim=384, configured_dim=768)
        assert exc.status_code == 500

    def test_collection_dimension_mismatch_message_contains_dimensions(self):
        exc = CollectionDimensionMismatchError("docs", existing_dim=384, configured_dim=768)
        assert "384" in exc.message
        assert "768" in exc.message
