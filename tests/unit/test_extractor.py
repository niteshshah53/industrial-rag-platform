"""
Unit tests for PDFExtractor.

Uses fpdf2 to generate real in-memory PDFs for testing extraction paths.
No external services required.
"""

import pytest
from fpdf import FPDF

from app.core.exceptions import InvalidFileTypeError, NoTextLayerError
from app.rag.extractor import PDFExtractor

# ── Helpers ────────────────────────────────────────────────────────────────────


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


# ── Tests ──────────────────────────────────────────────────────────────────────


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
        assert pages[0][0] == 1  # page_number is 1-indexed
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
        """A PDF with no text on any page raises NoTextLayerError."""
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
