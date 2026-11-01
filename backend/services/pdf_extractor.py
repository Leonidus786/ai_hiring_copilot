"""PDF text extraction with page-level provenance.

This module deliberately does not persist files or call external services.
The caller owns upload-size validation and any later storage/persistence.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

from pypdf import PdfReader


class PDFExtractionError(Exception):
    """Safe, machine-readable PDF extraction failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class ExtractedPage:
    """Text extracted from one 1-indexed PDF page."""

    page_number: int
    text: str


@dataclass(frozen=True, slots=True)
class PDFExtractionResult:
    """Page-aware extraction result used by later evidence-grounded phases."""

    pages: tuple[ExtractedPage, ...]

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def char_count(self) -> int:
        return sum(len(page.text) for page in self.pages)

    @property
    def full_text(self) -> str:
        """Build readable text without losing page boundaries."""
        non_empty_pages = [page for page in self.pages if page.text]
        return "\n\n".join(
            f"[Page {page.page_number}]\n{page.text}" for page in non_empty_pages
        )


def extract_pdf_bytes(
    pdf_bytes: bytes,
    max_pages: int = 20,
) -> PDFExtractionResult:
    """Extract page-indexed text from PDF bytes.

    Raises:
        PDFExtractionError: for empty, malformed, encrypted, oversized-page-count,
            or textless documents.
    """
    if not pdf_bytes:
        raise PDFExtractionError("EMPTY_FILE", "The uploaded file is empty.")

    if max_pages < 1:
        raise ValueError("max_pages must be a positive integer")

    # PDF headers are expected near the beginning of a file. The parser below
    # performs the actual structural validation; this is an early format check.
    if b"%PDF-" not in pdf_bytes[:1024]:
        raise PDFExtractionError(
            "INVALID_PDF_SIGNATURE",
            "The file does not contain a valid PDF header.",
        )

    try:
        reader = PdfReader(BytesIO(pdf_bytes), strict=True)
    except Exception as exc:
        raise PDFExtractionError(
            "MALFORMED_PDF", "The PDF is malformed or cannot be opened."
        ) from exc

    if reader.is_encrypted:
        raise PDFExtractionError(
            "ENCRYPTED_PDF", "Password-protected PDFs are not supported."
        )

    try:
        page_count = len(reader.pages)
    except Exception as exc:
        raise PDFExtractionError(
            "MALFORMED_PDF", "The PDF page structure could not be read."
        ) from exc

    if page_count == 0:
        raise PDFExtractionError("EMPTY_PDF", "The PDF contains no pages.")

    if page_count > max_pages:
        raise PDFExtractionError(
            "PAGE_LIMIT_EXCEEDED",
            f"The PDF has {page_count} pages; the limit is {max_pages}.",
        )

    extracted_pages: list[ExtractedPage] = []
    for page_number, page in enumerate(reader.pages, start=1):
        try:
            page_text = page.extract_text() or ""
        except Exception as exc:
            raise PDFExtractionError(
                "PAGE_EXTRACTION_FAILED",
                f"Text extraction failed on page {page_number}.",
            ) from exc

        extracted_pages.append(
            ExtractedPage(page_number=page_number, text=page_text.strip())
        )

    result = PDFExtractionResult(pages=tuple(extracted_pages))
    if not any(page.text for page in result.pages):
        raise PDFExtractionError(
            "NO_EXTRACTABLE_TEXT",
            "No machine-readable text was found. The PDF may be scanned or image-only.",
        )

    return result


def extract_text_from_pdf(file_path: str, max_pages: int = 20) -> str:
    """Backward-compatible path-based wrapper for existing callers."""
    try:
        with open(file_path, "rb") as pdf_file:
            pdf_bytes = pdf_file.read()
    except OSError as exc:
        raise PDFExtractionError(
            "PDF_READ_FAILED", "The PDF could not be read from storage."
        ) from exc

    return extract_pdf_bytes(pdf_bytes, max_pages=max_pages).full_text
