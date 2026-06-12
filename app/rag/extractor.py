"""
PDF text extraction using pdfplumber.

Responsibilities:
  - Validate PDF magic bytes (b"%PDF-") before any parsing
  - Detect password-protected PDFs
  - Extract text page-by-page, preserving page number metadata
  - Raise domain exceptions on unrecoverable failures

Design decisions:
  - Per-page extraction so downstream chunker can attach accurate page numbers
  - pdfplumber chosen over PyMuPDF for its reliable text ordering on
    multi-column layouts common in industrial manuals
  - Synchronous — callers must run this in a thread pool (run_in_executor)
    because pdfplumber performs blocking I/O

Usage:
    extractor = PDFExtractor()
    pages = extractor.extract(pdf_bytes, filename="manual.pdf")
    # pages: list of (page_number, text) tuples, page_number is 1-indexed
"""

import pdfplumber

from app.core.exceptions import InvalidFileTypeError, NoTextLayerError, PasswordProtectedError
from app.core.logging import get_logger

logger = get_logger(__name__)

_PDF_MAGIC = b"%PDF-"
_MIN_TEXT_CHARS = 50  # A page must have at least this many chars to count as having a text layer


class PDFExtractor:
    """
    Extracts page-level text from PDF byte content.

    Raises:
        InvalidFileTypeError: if the bytes are not a valid PDF
        PasswordProtectedError: if the PDF requires a password
        NoTextLayerError: if no page contains extractable text
    """

    def extract(self, content: bytes, filename: str) -> list[tuple[int, str]]:
        """
        Extract text from a PDF, returning one entry per page.

        Args:
            content: Raw PDF bytes.
            filename: Original filename, used only in error messages.

        Returns:
            List of (page_number, text) tuples. page_number is 1-indexed.
            Pages with no text are omitted from the result.

        Raises:
            InvalidFileTypeError: Magic bytes check failed.
            PasswordProtectedError: PDF requires a password to open.
            NoTextLayerError: No page produced enough text to be usable.
        """
        self._validate_magic_bytes(content, filename)

        pages = self._extract_pages(content, filename)

        if not pages:
            logger.warning("No text layer found in PDF", extra={"doc_filename": filename})
            raise NoTextLayerError(filename)

        total_chars = sum(len(text) for _, text in pages)
        logger.debug(
            "PDF extracted",
            extra={
                "doc_filename": filename,
                "page_count": len(pages),
                "total_chars": total_chars,
            },
        )
        return pages

    def _validate_magic_bytes(self, content: bytes, filename: str) -> None:
        """Reject non-PDF bytes before attempting to parse."""
        if not content[:5] == _PDF_MAGIC:
            raise InvalidFileTypeError(filename)

    def _extract_pages(self, content: bytes, filename: str) -> list[tuple[int, str]]:
        """
        Open the PDF with pdfplumber and extract text page by page.

        Returns only pages that contain at least _MIN_TEXT_CHARS characters
        of text, filtering out decorative/blank pages.
        """
        import io

        try:
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                if pdf.doc.encryption is not None:
                    raise PasswordProtectedError(filename)

                pages: list[tuple[int, str]] = []
                for page_num, page in enumerate(pdf.pages, start=1):
                    text = page.extract_text() or ""
                    text = text.strip()
                    if len(text) >= _MIN_TEXT_CHARS:
                        pages.append((page_num, text))

                return pages

        except (PasswordProtectedError, InvalidFileTypeError, NoTextLayerError):
            raise
        except Exception as exc:
            # pdfplumber raises various internal exceptions for corrupt files.
            # Map them all to InvalidFileTypeError since the bytes are not parseable.
            logger.warning(
                "pdfplumber failed to parse PDF",
                extra={"doc_filename": filename, "error": str(exc)},
            )
            raise InvalidFileTypeError(filename) from exc
