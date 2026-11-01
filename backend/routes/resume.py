"""Resume upload API.

Current batch validates and extracts PDFs in-memory. Persistence, authenticated
multi-tenancy, audit records, and retrieval/deletion endpoints are later Phase 1
acceptance items and are not claimed as implemented here.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from services.pdf_extractor import PDFExtractionError, extract_pdf_bytes

router = APIRouter()

DEFAULT_MAX_UPLOAD_SIZE_BYTES = 5 * 1024 * 1024
DEFAULT_MAX_PDF_PAGES = 20
UPLOAD_CHUNK_SIZE_BYTES = 64 * 1024


def _positive_int_setting(name: str, default: int) -> int:
    """Read a positive integer setting and fail clearly on invalid config."""
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a positive integer") from exc

    if value < 1:
        raise RuntimeError(f"{name} must be a positive integer")
    return value


MAX_UPLOAD_SIZE_BYTES = _positive_int_setting(
    "MAX_UPLOAD_SIZE_BYTES", DEFAULT_MAX_UPLOAD_SIZE_BYTES
)
MAX_PDF_PAGES = _positive_int_setting("MAX_PDF_PAGES", DEFAULT_MAX_PDF_PAGES)


def _http_error(status_code: int, error_code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"error_code": error_code, "message": message},
    )


@router.post("/upload")
async def upload_resume(file: UploadFile = File(...)) -> dict[str, object]:
    """Validate and extract an uploaded PDF without returning candidate PII."""
    try:
        filename = file.filename or ""
        if Path(filename).suffix.casefold() != ".pdf":
            raise _http_error(
                415, "UNSUPPORTED_FILE_EXTENSION", "Only PDF files are accepted."
            )

        if file.content_type != "application/pdf":
            raise _http_error(
                415, "UNSUPPORTED_MEDIA_TYPE", "Content-Type must be application/pdf."
            )

        chunks: list[bytes] = []
        total_bytes = 0
        header_prefix = bytearray()

        # Enforce the byte limit incrementally rather than trusting Content-Length
        # or reading an arbitrarily large upload into memory.
        while True:
            chunk = await file.read(UPLOAD_CHUNK_SIZE_BYTES)
            if not chunk:
                break

            total_bytes += len(chunk)
            if total_bytes > MAX_UPLOAD_SIZE_BYTES:
                raise _http_error(
                    413,
                    "FILE_TOO_LARGE",
                    f"The upload exceeds the {MAX_UPLOAD_SIZE_BYTES}-byte limit.",
                )

            if len(header_prefix) < 1024:
                remaining = 1024 - len(header_prefix)
                header_prefix.extend(chunk[:remaining])
            chunks.append(chunk)

        if total_bytes == 0:
            raise _http_error(400, "EMPTY_FILE", "The uploaded file is empty.")

        if b"%PDF-" not in header_prefix:
            raise _http_error(
                415,
                "INVALID_PDF_SIGNATURE",
                "The uploaded file does not have a valid PDF header.",
            )

        pdf_bytes = b"".join(chunks)
        try:
            extraction = await run_in_threadpool(
                extract_pdf_bytes, pdf_bytes, MAX_PDF_PAGES
            )
        except PDFExtractionError as exc:
            status_code = 413 if exc.code == "PAGE_LIMIT_EXCEEDED" else 422
            raise _http_error(status_code, exc.code, exc.message) from exc

        # Deliberately do not return original filename or extracted resume text.
        # This endpoint is still stateless in this batch; later work adds storage
        # and database metadata under authenticated tenant ownership.
        return {
            "status": "success",
            "processing_status": "EXTRACTED",
            "file_size_bytes": total_bytes,
            "page_count": extraction.page_count,
            "char_count": extraction.char_count,
        }
    finally:
        await file.close()
