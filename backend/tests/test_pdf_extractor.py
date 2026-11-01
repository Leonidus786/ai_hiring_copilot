from __future__ import annotations

from io import BytesIO

import pytest
from pypdf import PdfWriter
from reportlab.pdfgen import canvas

from services.pdf_extractor import PDFExtractionError, extract_pdf_bytes


def make_text_pdf(*page_texts: str) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    for page_text in page_texts:
        pdf.drawString(72, 720, page_text)
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def make_blank_pdf() -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def make_encrypted_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.encrypt(user_password="test-password")
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def test_extract_pdf_preserves_page_boundaries() -> None:
    result = extract_pdf_bytes(make_text_pdf("Python and FastAPI", "PostgreSQL"))
    assert result.page_count == 2
    assert result.pages[0].page_number == 1
    assert "Python and FastAPI" in result.pages[0].text
    assert result.pages[1].page_number == 2
    assert "PostgreSQL" in result.pages[1].text
    assert "[Page 1]" in result.full_text
    assert "[Page 2]" in result.full_text


def test_extract_pdf_rejects_invalid_signature() -> None:
    with pytest.raises(PDFExtractionError) as error:
        extract_pdf_bytes(b"not a pdf")
    assert error.value.code == "INVALID_PDF_SIGNATURE"


def test_extract_pdf_rejects_malformed_pdf() -> None:
    with pytest.raises(PDFExtractionError) as error:
        extract_pdf_bytes(b"%PDF-1.7\nthis is not a valid PDF structure")
    assert error.value.code == "MALFORMED_PDF"


def test_extract_pdf_rejects_encrypted_pdf() -> None:
    with pytest.raises(PDFExtractionError) as error:
        extract_pdf_bytes(make_encrypted_pdf())
    assert error.value.code == "ENCRYPTED_PDF"


def test_extract_pdf_enforces_page_limit() -> None:
    with pytest.raises(PDFExtractionError) as error:
        extract_pdf_bytes(make_text_pdf("page one", "page two"), max_pages=1)
    assert error.value.code == "PAGE_LIMIT_EXCEEDED"


def test_extract_pdf_rejects_image_only_or_textless_pdf() -> None:
    with pytest.raises(PDFExtractionError) as error:
        extract_pdf_bytes(make_blank_pdf())
    assert error.value.code == "NO_EXTRACTABLE_TEXT"


def test_upload_endpoint_returns_metadata_without_resume_text(client) -> None:
    resume_text = "Synthetic candidate profile: Python and FastAPI."
    response = client.post(
        "/api/resume/upload",
        files={"file": ("sample.pdf", make_text_pdf(resume_text), "application/pdf")},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["processing_status"] == "EXTRACTED"
    assert payload["page_count"] == 1
    assert payload["char_count"] > 0
    assert payload["duplicate"] is False
    assert "extracted_text" not in payload
    assert resume_text not in response.text
    assert "filename" not in payload
    assert response.headers.get("X-Request-ID")


def test_upload_endpoint_rejects_non_pdf_extension(client) -> None:
    response = client.post(
        "/api/resume/upload",
        files={"file": ("sample.txt", b"not a pdf", "application/pdf")},
    )
    assert response.status_code == 415
    assert response.json()["detail"]["error_code"] == "UNSUPPORTED_FILE_EXTENSION"


def test_upload_endpoint_rejects_wrong_content_type(client) -> None:
    response = client.post(
        "/api/resume/upload",
        files={"file": ("sample.pdf", b"%PDF-1.7 fake", "text/plain")},
    )
    assert response.status_code == 415
    assert response.json()["detail"]["error_code"] == "UNSUPPORTED_MEDIA_TYPE"


def test_upload_endpoint_rejects_invalid_pdf_signature(client) -> None:
    response = client.post(
        "/api/resume/upload",
        files={"file": ("sample.pdf", b"not a pdf", "application/pdf")},
    )
    assert response.status_code == 415
    assert response.json()["detail"]["error_code"] == "INVALID_PDF_SIGNATURE"


def test_upload_endpoint_rejects_blank_pdf(client) -> None:
    response = client.post(
        "/api/resume/upload",
        files={"file": ("blank.pdf", make_blank_pdf(), "application/pdf")},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["error_code"] == "NO_EXTRACTABLE_TEXT"


def test_upload_endpoint_enforces_upload_size_limit(client, monkeypatch) -> None:
    from routes import resume as resume_route
    monkeypatch.setattr(resume_route, "MAX_UPLOAD_SIZE_BYTES", 32)
    response = client.post(
        "/api/resume/upload",
        files={"file": ("large.pdf", b"%PDF-1.7" + b"x" * 40, "application/pdf")},
    )
    assert response.status_code == 413
    assert response.json()["detail"]["error_code"] == "FILE_TOO_LARGE"


def test_upload_endpoint_enforces_page_limit(client, monkeypatch) -> None:
    from routes import resume as resume_route
    monkeypatch.setattr(resume_route, "MAX_PDF_PAGES", 1)
    response = client.post(
        "/api/resume/upload",
        files={"file": ("two-pages.pdf", make_text_pdf("page one", "page two"), "application/pdf")},
    )
    assert response.status_code == 413
    assert response.json()["detail"]["error_code"] == "PAGE_LIMIT_EXCEEDED"


def test_upload_endpoint_rejects_encrypted_pdf(client) -> None:
    response = client.post(
        "/api/resume/upload",
        files={"file": ("encrypted.pdf", make_encrypted_pdf(), "application/pdf")},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["error_code"] == "ENCRYPTED_PDF"
