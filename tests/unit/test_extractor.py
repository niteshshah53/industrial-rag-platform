"""
Unit tests for all document extractors and the get_extractor factory.

Covers:
  - PDFExtractor   (pdfplumber — real in-memory PDFs via fpdf2)
  - DocxExtractor  (python-docx — real in-memory DOCX files)
  - TxtExtractor   (plain bytes — UTF-8 and latin-1)
  - get_extractor  (factory routing + InvalidFileTypeError for unknowns)

No external services required.
"""

import io

import pytest
from fpdf import FPDF

from app.core.exceptions import InvalidFileTypeError, NoTextLayerError
from app.rag.extractor import (
    DocxExtractor,
    PDFExtractor,
    TxtExtractor,
    get_extractor,
)

# ── PDF helpers ────────────────────────────────────────────────────────────────


def _make_pdf(pages: list[str]) -> bytes:
    """Generate a minimal valid PDF with the given text on each page."""
    pdf = FPDF()
    pdf.set_font("Helvetica", size=12)
    for text in pages:
        pdf.add_page()
        pdf.multi_cell(0, 10, text)
    return pdf.output()


def _make_empty_pdf() -> bytes:
    """Generate a PDF with pages that have no text content."""
    pdf = FPDF()
    pdf.add_page()
    return pdf.output()


# ── DOCX helpers ───────────────────────────────────────────────────────────────


def _make_docx(paragraphs: list[str]) -> bytes:
    """Generate a minimal DOCX in memory with the given paragraphs."""
    from docx import Document

    doc = Document()
    for para in paragraphs:
        doc.add_paragraph(para)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ── TestPDFExtractor ───────────────────────────────────────────────────────────


class TestPDFExtractorValidMagicBytes:
    def test_rejects_non_pdf_bytes(self):
        extractor = PDFExtractor()
        with pytest.raises(InvalidFileTypeError):
            extractor.extract(b"not a pdf at all", "fake.pdf")

    def test_rejects_html_content(self):
        extractor = PDFExtractor()
        with pytest.raises(InvalidFileTypeError):
            extractor.extract(b"<html><body>Hello</body></html>", "page.html")

    def test_rejects_empty_bytes(self):
        extractor = PDFExtractor()
        with pytest.raises(InvalidFileTypeError):
            extractor.extract(b"", "empty.pdf")


class TestPDFExtractorTextExtraction:
    def test_single_page_extraction(self):
        content = _make_pdf(["This is a technical manual page with sufficient text content."])
        extractor = PDFExtractor()
        pages = extractor.extract(content, "manual.pdf")
        assert len(pages) == 1
        assert pages[0][0] == 1
        assert "technical manual" in pages[0][1]

    def test_multi_page_extraction(self):
        texts = [
            "Page one contains safety warnings and important operational notes.",
            "Page two describes the hydraulic system components and their functions.",
            "Page three provides maintenance schedules for routine service intervals.",
        ]
        content = _make_pdf(texts)
        extractor = PDFExtractor()
        pages = extractor.extract(content, "manual.pdf")
        assert len(pages) == 3
        assert pages[0][0] == 1
        assert pages[1][0] == 2
        assert pages[2][0] == 3

    def test_returns_list_of_tuples(self):
        content = _make_pdf(["Sufficient text content for the extractor to accept this page."])
        extractor = PDFExtractor()
        pages = extractor.extract(content, "doc.pdf")
        assert isinstance(pages, list)
        assert isinstance(pages[0], tuple)
        assert len(pages[0]) == 2

    def test_page_numbers_are_one_indexed(self):
        content = _make_pdf(
            [
                "First page with plenty of text content for extraction.",
                "Second page with more detailed technical information.",
            ]
        )
        extractor = PDFExtractor()
        pages = extractor.extract(content, "doc.pdf")
        page_numbers = [p[0] for p in pages]
        assert 1 in page_numbers
        assert 2 in page_numbers
        assert 0 not in page_numbers


class TestPDFExtractorNoTextLayer:
    def test_raises_no_text_layer_for_empty_pdf(self):
        content = _make_empty_pdf()
        extractor = PDFExtractor()
        with pytest.raises(NoTextLayerError):
            extractor.extract(content, "scan.pdf")


class TestPDFExtractorFilenameInErrors:
    def test_invalid_file_type_error_contains_filename(self):
        extractor = PDFExtractor()
        try:
            extractor.extract(b"garbage", "myfile.exe")
        except InvalidFileTypeError as exc:
            assert "myfile.exe" in exc.message

    def test_no_text_layer_error_contains_filename(self):
        content = _make_empty_pdf()
        extractor = PDFExtractor()
        try:
            extractor.extract(content, "scanned_doc.pdf")
        except NoTextLayerError as exc:
            assert "scanned_doc.pdf" in exc.message


# ── TestDocxExtractor ──────────────────────────────────────────────────────────


class TestDocxExtractorTextExtraction:
    def test_extracts_text_from_valid_docx(self):
        content = _make_docx(["Hydraulic pump specifications and torque values for maintenance."])
        extractor = DocxExtractor()
        pages = extractor.extract(content, "manual.docx")
        assert len(pages) >= 1
        assert pages[0][0] == 1
        assert "Hydraulic" in pages[0][1]

    def test_page_numbers_are_one_indexed(self):
        content = _make_docx(["First section of the document.", "Second section here."])
        extractor = DocxExtractor()
        pages = extractor.extract(content, "doc.docx")
        assert pages[0][0] == 1

    def test_returns_list_of_tuples(self):
        content = _make_docx(["Some paragraph text with sufficient content to extract."])
        extractor = DocxExtractor()
        pages = extractor.extract(content, "doc.docx")
        assert isinstance(pages, list)
        assert isinstance(pages[0], tuple)
        assert len(pages[0]) == 2

    def test_long_document_splits_into_multiple_virtual_pages(self):
        # Create enough text to exceed one virtual page (~3000 chars)
        long_para = "A" * 400 + " industrial specification details here."
        paragraphs = [long_para] * 10  # ~4400+ chars total
        content = _make_docx(paragraphs)
        extractor = DocxExtractor()
        pages = extractor.extract(content, "long.docx")
        assert len(pages) >= 2, "Long document should produce multiple virtual pages"

    def test_all_paragraph_text_is_preserved(self):
        content = _make_docx(["Alpha paragraph.", "Beta paragraph.", "Gamma paragraph."])
        extractor = DocxExtractor()
        pages = extractor.extract(content, "doc.docx")
        full_text = " ".join(text for _, text in pages)
        assert "Alpha" in full_text
        assert "Beta" in full_text
        assert "Gamma" in full_text


class TestDocxExtractorErrorCases:
    def test_raises_no_text_layer_for_empty_docx(self):
        content = _make_docx([])  # No paragraphs
        extractor = DocxExtractor()
        with pytest.raises(NoTextLayerError):
            extractor.extract(content, "empty.docx")

    def test_raises_invalid_file_type_for_random_bytes(self):
        extractor = DocxExtractor()
        with pytest.raises(InvalidFileTypeError):
            extractor.extract(b"this is not a zip or docx file at all", "fake.docx")

    def test_no_text_layer_error_contains_filename(self):
        content = _make_docx([])
        extractor = DocxExtractor()
        try:
            extractor.extract(content, "blank.docx")
        except NoTextLayerError as exc:
            assert "blank.docx" in exc.message


# ── TestTxtExtractor ───────────────────────────────────────────────────────────


class TestTxtExtractorTextExtraction:
    def test_extracts_utf8_text(self):
        content = b"This is a plain text document with enough content to be extracted."
        extractor = TxtExtractor()
        pages = extractor.extract(content, "notes.txt")
        assert len(pages) >= 1
        assert pages[0][0] == 1
        assert "plain text" in pages[0][1]

    def test_extracts_latin1_encoded_text(self):
        # latin-1 encoded text with non-UTF-8 byte (0xe9 = é)
        content = "Pr\xe9sentation technique des syst\xe8mes hydrauliques.".encode("latin-1")
        content = content + b" " + b"x" * 60  # ensure > _MIN_PAGE_CHARS
        extractor = TxtExtractor()
        pages = extractor.extract(content, "doc.txt")
        assert len(pages) >= 1

    def test_page_numbers_are_one_indexed(self):
        content = b"Short content that fits in one virtual page. " + b"word " * 20
        extractor = TxtExtractor()
        pages = extractor.extract(content, "doc.txt")
        assert pages[0][0] == 1

    def test_long_text_splits_into_multiple_virtual_pages(self):
        # Create text well over 3000 chars
        content = ("Industrial maintenance procedure. " * 100).encode("utf-8")
        extractor = TxtExtractor()
        pages = extractor.extract(content, "manual.txt")
        assert len(pages) >= 2

    def test_all_content_preserved_across_pages(self):
        # Build text where first and last words are far apart
        text = "START " + ("middle content. " * 200) + " END"
        content = text.encode("utf-8")
        extractor = TxtExtractor()
        pages = extractor.extract(content, "doc.txt")
        full = " ".join(t for _, t in pages)
        assert "START" in full
        assert "END" in full


class TestTxtExtractorErrorCases:
    def test_raises_no_text_layer_for_empty_bytes(self):
        extractor = TxtExtractor()
        with pytest.raises(NoTextLayerError):
            extractor.extract(b"", "empty.txt")

    def test_raises_no_text_layer_for_whitespace_only(self):
        extractor = TxtExtractor()
        with pytest.raises(NoTextLayerError):
            extractor.extract(b"   \n\n\t  ", "blank.txt")

    def test_raises_no_text_layer_for_too_short_content(self):
        extractor = TxtExtractor()
        with pytest.raises(NoTextLayerError):
            extractor.extract(b"hi", "tiny.txt")

    def test_no_text_layer_error_contains_filename(self):
        extractor = TxtExtractor()
        try:
            extractor.extract(b"", "myfile.txt")
        except NoTextLayerError as exc:
            assert "myfile.txt" in exc.message


# ── TestGetExtractor factory ───────────────────────────────────────────────────


class TestGetExtractor:
    def test_returns_pdf_extractor_for_pdf_magic_bytes(self):
        content = _make_pdf(["Some text."])
        extractor = get_extractor(content, "manual.pdf")
        assert isinstance(extractor, PDFExtractor)

    def test_returns_pdf_extractor_regardless_of_extension(self):
        # PDF magic bytes override the extension
        content = _make_pdf(["Some text."])
        extractor = get_extractor(content, "renamed_file.bin")
        assert isinstance(extractor, PDFExtractor)

    def test_returns_docx_extractor_for_docx_file(self):
        content = _make_docx(["Some DOCX paragraph text."])
        extractor = get_extractor(content, "report.docx")
        assert isinstance(extractor, DocxExtractor)

    def test_returns_txt_extractor_for_txt_filename(self):
        content = b"Plain text content that is long enough to pass the minimum check threshold."
        extractor = get_extractor(content, "readme.txt")
        assert isinstance(extractor, TxtExtractor)

    def test_raises_invalid_file_type_for_unsupported_extension(self):
        content = b"<html><body>some page</body></html>"
        with pytest.raises(InvalidFileTypeError):
            get_extractor(content, "page.html")

    def test_raises_invalid_file_type_for_zip_without_docx_extension(self):
        # XLSX is also a ZIP archive — should be rejected (not DOCX)
        content = _make_docx(["text"])  # ZIP magic bytes, but wrong extension
        with pytest.raises(InvalidFileTypeError):
            get_extractor(content, "spreadsheet.xlsx")

    def test_raises_invalid_file_type_for_empty_bytes_unknown_extension(self):
        with pytest.raises(InvalidFileTypeError):
            get_extractor(b"", "unknown.xyz")

    def test_error_message_lists_supported_types(self):
        try:
            get_extractor(b"random garbage bytes", "file.exe")
        except InvalidFileTypeError as exc:
            assert "PDF" in exc.message
            assert "DOCX" in exc.message
            assert "TXT" in exc.message

    def test_docx_extractor_extension_case_insensitive(self):
        content = _make_docx(["Some content here."])
        extractor = get_extractor(content, "REPORT.DOCX")
        assert isinstance(extractor, DocxExtractor)

    def test_txt_extractor_extension_case_insensitive(self):
        content = b"Content long enough to satisfy the minimum page character threshold."
        extractor = get_extractor(content, "README.TXT")
        assert isinstance(extractor, TxtExtractor)
