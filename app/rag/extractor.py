"""
Document text extraction — PDF, DOCX, and plain-text formats.

Each extractor class implements a single public method:

    extract(content: bytes, filename: str) -> list[tuple[int, str]]

returning a list of (page_number, text) tuples where page_number is
1-indexed.  PDF pages map directly to physical pages; DOCX and TXT use
virtual pages of ~3 000 characters (roughly one printed page) so that
downstream chunking still gets accurate page-number metadata.

Extractor selection
-------------------
Use the factory function rather than instantiating extractors directly:

    extractor = get_extractor(content, filename)
    pages = extractor.extract(content, filename)

get_extractor() inspects magic bytes and the file extension to pick the
right implementation.  It raises InvalidFileTypeError for any unsupported
format, so callers get a consistent error regardless of which format was
attempted.

Format detection strategy
--------------------------
- PDF:  magic bytes b"%PDF-" (extension-independent).
- DOCX: magic bytes b"PK\\x03\\x04" (ZIP archive) *and* .docx extension.
        (XLSX/PPTX also start with the ZIP magic; the extension
        disambiguates them.)
- TXT:  .txt extension only (no reliable magic bytes for plain text).

Design decisions
----------------
- All extractors are synchronous — callers must run them in a thread pool
  (asyncio.get_event_loop().run_in_executor) to avoid blocking the event loop.
- pdfplumber is used for PDF over PyMuPDF for reliable text ordering on
  multi-column industrial documents.
- python-docx is used for DOCX extraction; tables are intentionally
  skipped in this release (Phase 5) as table data in industrial manuals
  is rarely the primary narrative content and can confuse the chunker.
- TXT encoding detection: try UTF-8 first, fall back to latin-1 (covers
  virtually all Western-language industrial documentation).
"""

from __future__ import annotations

import io

import pdfplumber

from app.core.exceptions import InvalidFileTypeError, NoTextLayerError, PasswordProtectedError
from app.core.logging import get_logger

logger = get_logger(__name__)

_PDF_MAGIC = b"%PDF-"
_DOCX_MAGIC = b"PK\x03\x04"

# Minimum characters for a page to be considered non-empty.
_MIN_PAGE_CHARS = 50

# Target size for DOCX/TXT virtual pages (~750 words ≈ one printed page).
_VIRTUAL_PAGE_CHARS = 3_000


# ── Shared helpers ─────────────────────────────────────────────────────────────


def _split_into_virtual_pages(text: str) -> list[tuple[int, str]]:
    """
    Divide a long string into virtual pages of ~_VIRTUAL_PAGE_CHARS characters.

    Prefers to break at paragraph boundaries (double newlines) within the
    last 25 % of each page window to avoid cutting mid-sentence.

    Args:
        text: Pre-stripped document text.

    Returns:
        List of (page_number, text) tuples; page_number is 1-indexed.
    """
    pages: list[tuple[int, str]] = []
    page_num = 1
    start = 0

    while start < len(text):
        end = start + _VIRTUAL_PAGE_CHARS

        if end < len(text):
            # Try to break on a paragraph boundary within the back quarter.
            search_from = start + (_VIRTUAL_PAGE_CHARS * 3 // 4)
            break_pos = text.rfind("\n\n", search_from, end)
            if break_pos > 0:
                end = break_pos + 2  # consume the blank line

        chunk = text[start:end].strip()
        if chunk:
            pages.append((page_num, chunk))
            page_num += 1

        start = end

    return pages


# ── PDF ────────────────────────────────────────────────────────────────────────


class PDFExtractor:
    """
    Extracts page-level text from PDF byte content via pdfplumber.

    Raises:
        InvalidFileTypeError:  bytes are not a valid PDF.
        PasswordProtectedError: PDF requires a password.
        NoTextLayerError:       no page contains extractable text (scanned PDF).
    """

    def extract(self, content: bytes, filename: str) -> list[tuple[int, str]]:
        """
        Extract text from a PDF, returning one entry per non-empty page.

        Args:
            content:  Raw PDF bytes.
            filename: Original filename (used in error messages only).

        Returns:
            List of (page_number, text) tuples; page_number is 1-indexed.
        """
        if content[:5] != _PDF_MAGIC:
            raise InvalidFileTypeError(filename)

        pages = self._extract_pages(content, filename)

        if not pages:
            logger.warning("No text layer found in PDF", extra={"doc_filename": filename})
            raise NoTextLayerError(filename)

        total_chars = sum(len(t) for _, t in pages)
        logger.debug(
            "PDF extracted",
            extra={
                "doc_filename": filename,
                "page_count": len(pages),
                "total_chars": total_chars,
            },
        )
        return pages

    def _extract_pages(self, content: bytes, filename: str) -> list[tuple[int, str]]:
        try:
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                if pdf.doc.encryption is not None:
                    raise PasswordProtectedError(filename)

                pages: list[tuple[int, str]] = []
                for page_num, page in enumerate(pdf.pages, start=1):
                    text = (page.extract_text() or "").strip()
                    if len(text) >= _MIN_PAGE_CHARS:
                        pages.append((page_num, text))

                return pages

        except (PasswordProtectedError, InvalidFileTypeError, NoTextLayerError):
            raise
        except Exception as exc:
            logger.warning(
                "pdfplumber failed to parse PDF",
                extra={"doc_filename": filename, "error": str(exc)},
            )
            raise InvalidFileTypeError(filename) from exc


# ── DOCX ───────────────────────────────────────────────────────────────────────


class DocxExtractor:
    """
    Extracts text from DOCX byte content via python-docx.

    DOCX files have no reliable physical page boundaries, so paragraphs are
    grouped into virtual pages of ~_VIRTUAL_PAGE_CHARS characters.  This
    gives downstream chunking accurate page-number metadata for citations
    even though the numbers are virtual rather than real.

    Only body paragraphs are extracted.  Tables are omitted in this release.

    Raises:
        InvalidFileTypeError: bytes cannot be parsed as a DOCX file.
        NoTextLayerError:     document contains no paragraph text.
    """

    def extract(self, content: bytes, filename: str) -> list[tuple[int, str]]:
        """
        Extract text from a DOCX file as virtual pages.

        Args:
            content:  Raw DOCX bytes.
            filename: Original filename (used in error messages only).

        Returns:
            List of (page_number, text) tuples; page_number is 1-indexed virtual.
        """
        from docx import Document  # python-docx; imported lazily to keep startup fast

        try:
            doc = Document(io.BytesIO(content))
        except Exception as exc:
            logger.warning(
                "python-docx failed to parse file",
                extra={"doc_filename": filename, "error": str(exc)},
            )
            raise InvalidFileTypeError(filename) from exc

        # Collect non-empty paragraph texts.
        paras = [p.text.strip() for p in doc.paragraphs if p.text.strip()]

        if not paras:
            raise NoTextLayerError(filename)

        # Join paragraphs with double newlines so _split_into_virtual_pages
        # can break on paragraph boundaries.
        full_text = "\n\n".join(paras)
        pages = _split_into_virtual_pages(full_text)

        total_chars = sum(len(t) for _, t in pages)
        logger.debug(
            "DOCX extracted",
            extra={
                "doc_filename": filename,
                "virtual_pages": len(pages),
                "total_chars": total_chars,
            },
        )
        return pages


# ── Plain text ─────────────────────────────────────────────────────────────────


class TxtExtractor:
    """
    Extracts text from plain-text byte content.

    Encoding detection: attempts UTF-8 first; falls back to latin-1 (covers
    virtually all Western-language industrial documentation).

    Like DOCX, plain text has no page structure, so the content is divided
    into virtual pages of ~_VIRTUAL_PAGE_CHARS characters.

    Raises:
        NoTextLayerError: file is empty or contains only whitespace.
    """

    def extract(self, content: bytes, filename: str) -> list[tuple[int, str]]:
        """
        Decode and split plain text into virtual pages.

        Args:
            content:  Raw file bytes.
            filename: Original filename (used in error messages only).

        Returns:
            List of (page_number, text) tuples; page_number is 1-indexed virtual.
        """
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            text = content.decode("latin-1")

        text = text.strip()
        if len(text) < _MIN_PAGE_CHARS:
            raise NoTextLayerError(filename)

        pages = _split_into_virtual_pages(text)

        logger.debug(
            "TXT extracted",
            extra={
                "doc_filename": filename,
                "virtual_pages": len(pages),
                "total_chars": len(text),
            },
        )
        return pages


# ── Factory ────────────────────────────────────────────────────────────────────

_SUPPORTED_TYPES = ["PDF", "DOCX", "TXT"]


def get_extractor(content: bytes, filename: str) -> PDFExtractor | DocxExtractor | TxtExtractor:
    """
    Return the appropriate extractor for the given file content and name.

    Detection order:
      1. PDF   — magic bytes b"%PDF-" (extension-independent)
      2. DOCX  — magic bytes b"PK\\x03\\x04" *and* .docx extension
      3. TXT   — .txt extension (no reliable magic bytes)
      4. Otherwise — raise InvalidFileTypeError

    Args:
        content:  Raw file bytes (at least the first 4 bytes must be present).
        filename: Original filename; extension is used to disambiguate formats
                  that share ZIP magic bytes (e.g. DOCX vs XLSX).

    Returns:
        An extractor instance whose extract() method accepts the same
        (content, filename) arguments.

    Raises:
        InvalidFileTypeError: Format is not supported.
    """
    lower = filename.lower()

    if content[:5] == _PDF_MAGIC:
        return PDFExtractor()

    if content[:4] == _DOCX_MAGIC and lower.endswith(".docx"):
        return DocxExtractor()

    if lower.endswith(".txt"):
        return TxtExtractor()

    raise InvalidFileTypeError(filename, supported_types=_SUPPORTED_TYPES)
