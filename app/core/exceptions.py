"""
Application exception hierarchy.

All exceptions raised by business logic inherit from AppError. Each
exception carries:
  - message: a human-readable description safe to return to the caller
  - code: a machine-readable ErrorCode enum value for API consumers
  - status_code: the HTTP status code the API layer should respond with

The FastAPI exception handler in main.py converts AppError subclasses
into the standard error response shape:

    {
        "detail": {
            "code": "DOCUMENT_NOT_FOUND",
            "message": "Document a3f2b1c0 does not exist.",
            "request_id": "..."
        }
    }

Usage:
    from app.core.exceptions import DocumentNotFoundError
    raise DocumentNotFoundError(document_id="a3f2b1c0")
"""

from enum import StrEnum

# ── Error Codes ───────────────────────────────────────────────────────────────


class ErrorCode(StrEnum):
    """Machine-readable error codes returned in API error responses."""

    # Document management
    DOCUMENT_NOT_FOUND = "DOCUMENT_NOT_FOUND"
    DOCUMENT_ALREADY_EXISTS = "DOCUMENT_ALREADY_EXISTS"

    # File validation
    INVALID_FILE_TYPE = "INVALID_FILE_TYPE"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"

    # Ingestion pipeline failures
    PASSWORD_PROTECTED = "PASSWORD_PROTECTED"
    NO_TEXT_LAYER = "NO_TEXT_LAYER"
    INGESTION_FAILED = "INGESTION_FAILED"

    # Query pipeline failures
    NO_DOCUMENTS_FOUND = "NO_DOCUMENTS_FOUND"
    QUERY_FAILED = "QUERY_FAILED"

    # Infrastructure
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    COLLECTION_DIMENSION_MISMATCH = "COLLECTION_DIMENSION_MISMATCH"

    # Catch-all
    INTERNAL_ERROR = "INTERNAL_ERROR"


# ── Base Exception ────────────────────────────────────────────────────────────


class AppError(Exception):
    """
    Base class for all application-level errors.

    Subclass this for every domain error rather than raising generic
    exceptions. The FastAPI exception handler catches AppError and
    converts it to a structured JSON response automatically.
    """

    def __init__(
        self,
        message: str,
        code: ErrorCode,
        status_code: int = 500,
    ) -> None:
        self.message = message
        self.code = code
        self.status_code = status_code
        super().__init__(message)

    def __repr__(self) -> str:
        return f"{type(self).__name__}(code={self.code}, status={self.status_code})"


# ── Document Exceptions ───────────────────────────────────────────────────────


class DocumentNotFoundError(AppError):
    """Raised when a document_id does not exist in the registry."""

    def __init__(self, document_id: str) -> None:
        super().__init__(
            message=f"Document '{document_id}' does not exist.",
            code=ErrorCode.DOCUMENT_NOT_FOUND,
            status_code=404,
        )
        self.document_id = document_id


class DocumentAlreadyExistsError(AppError):
    """
    Raised when an uploaded file is a duplicate of an existing document.
    The existing document_id is included so the caller can reference it.
    """

    def __init__(self, document_id: str, filename: str) -> None:
        super().__init__(
            message=(
                f"A document with the same content already exists "
                f"(document_id='{document_id}', filename='{filename}'). "
                "Use the existing document or delete it first."
            ),
            code=ErrorCode.DOCUMENT_ALREADY_EXISTS,
            status_code=409,
        )
        self.document_id = document_id
        self.filename = filename


# ── File Validation Exceptions ────────────────────────────────────────────────


class InvalidFileTypeError(AppError):
    """
    Raised when the uploaded file is not a supported type (PDF, DOCX, or TXT).
    Detection uses magic bytes for PDF/DOCX; TXT falls back to file extension.
    """

    def __init__(self, filename: str, supported_types: list[str] | None = None) -> None:
        supported = supported_types or ["PDF", "DOCX", "TXT"]
        super().__init__(
            message=(
                f"File '{filename}' is not a supported document type. "
                f"Supported types: {', '.join(supported)}."
            ),
            code=ErrorCode.INVALID_FILE_TYPE,
            status_code=422,
        )
        self.filename = filename


class FileTooLargeError(AppError):
    """Raised when the uploaded file exceeds the configured size limit."""

    def __init__(self, filename: str, size_mb: float, max_mb: int) -> None:
        super().__init__(
            message=(
                f"File '{filename}' is {size_mb:.1f} MB, which exceeds "
                f"the maximum allowed size of {max_mb} MB."
            ),
            code=ErrorCode.FILE_TOO_LARGE,
            status_code=422,
        )
        self.filename = filename
        self.size_mb = size_mb
        self.max_mb = max_mb


# ── Ingestion Exceptions ──────────────────────────────────────────────────────


class IngestionError(AppError):
    """Base class for failures during the document ingestion pipeline."""

    def __init__(
        self,
        message: str,
        code: ErrorCode = ErrorCode.INGESTION_FAILED,
        status_code: int = 500,
    ) -> None:
        super().__init__(message=message, code=code, status_code=status_code)


class PasswordProtectedError(IngestionError):
    """Raised when a PDF is password-protected and cannot be extracted."""

    def __init__(self, filename: str) -> None:
        super().__init__(
            message=(
                f"File '{filename}' is password-protected and cannot be processed. "
                "Please provide an unlocked PDF."
            ),
            code=ErrorCode.PASSWORD_PROTECTED,
            status_code=422,
        )
        self.filename = filename


class NoTextLayerError(IngestionError):
    """
    Raised when a PDF contains no extractable text layer.
    This typically indicates a scanned document without OCR.
    """

    def __init__(self, filename: str) -> None:
        super().__init__(
            message=(
                f"File '{filename}' contains no text layer. "
                "Scanned PDFs require OCR before ingestion, which is not "
                "currently supported."
            ),
            code=ErrorCode.NO_TEXT_LAYER,
            status_code=422,
        )
        self.filename = filename


# ── Query Exceptions ──────────────────────────────────────────────────────────


class QueryError(AppError):
    """Base class for failures during the query / RAG pipeline."""

    def __init__(self, message: str, status_code: int = 500) -> None:
        super().__init__(
            message=message,
            code=ErrorCode.QUERY_FAILED,
            status_code=status_code,
        )


# ── Infrastructure Exceptions ─────────────────────────────────────────────────


class ServiceUnavailableError(AppError):
    """
    Raised when a required external service (Ollama, Qdrant) is unreachable.
    Maps to HTTP 503 so load balancers remove the pod from rotation.
    """

    def __init__(self, service: str, detail: str = "") -> None:
        msg = f"Service '{service}' is currently unavailable."
        if detail:
            msg = f"{msg} Detail: {detail}"
        super().__init__(
            message=msg,
            code=ErrorCode.SERVICE_UNAVAILABLE,
            status_code=503,
        )
        self.service = service


class CollectionDimensionMismatchError(AppError):
    """
    Raised on startup when the existing Qdrant collection was created with
    different vector dimensions than those configured in settings.

    This requires operator intervention — the collection must be deleted
    and recreated, or the EMBEDDING_DIMENSIONS setting must be corrected.
    """

    def __init__(self, collection: str, existing_dim: int, configured_dim: int) -> None:
        super().__init__(
            message=(
                f"Qdrant collection '{collection}' was created with {existing_dim} dimensions "
                f"but EMBEDDING_DIMENSIONS is set to {configured_dim}. "
                "Delete the collection and restart, or correct EMBEDDING_DIMENSIONS."
            ),
            code=ErrorCode.COLLECTION_DIMENSION_MISMATCH,
            status_code=500,
        )
        self.collection = collection
        self.existing_dim = existing_dim
        self.configured_dim = configured_dim
