"""Tenant-scoped resume ingestion and lifecycle endpoints."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from sqlalchemy import func, select
from sqlalchemy.sql import Select
from sqlalchemy.orm import Session

from dependencies import RequestIdentity, get_db, get_identity, get_request_id, get_storage
from models import AuditLog, Resume
from schemas import DeleteResponse, ResumeListResponse, ResumeMetadataResponse, ResumeUploadResponse
from services.pdf_extractor import PDFExtractionError, extract_pdf_bytes
from services.resume_service import ResumeDeletionPendingError, delete_resume, ingest_resume
from services.storage import StorageAdapter, StorageError

router = APIRouter()
DEFAULT_MAX_UPLOAD_SIZE_BYTES = 5 * 1024 * 1024
DEFAULT_MAX_PDF_PAGES = 20
UPLOAD_CHUNK_SIZE_BYTES = 64 * 1024


def _positive_int_setting(name: str, default: int) -> int:
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


MAX_UPLOAD_SIZE_BYTES = _positive_int_setting("MAX_UPLOAD_SIZE_BYTES", DEFAULT_MAX_UPLOAD_SIZE_BYTES)
MAX_PDF_PAGES = _positive_int_setting("MAX_PDF_PAGES", DEFAULT_MAX_PDF_PAGES)


def _http_error(status_code: int, error_code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"error_code": error_code, "message": message})


def _visible_resume_query(tenant_id: str, resume_id: UUID) -> Select[tuple[Resume]]:
    return select(Resume).where(
        Resume.id == str(resume_id),
        Resume.tenant_id == tenant_id,
        Resume.processing_status != "DELETION_PENDING",
    )


@router.post("/upload", response_model=ResumeUploadResponse)
def upload_resume(
    request: Request,
    file: UploadFile = File(...),
    identity: RequestIdentity = Depends(get_identity),
    db: Session = Depends(get_db),
    storage: StorageAdapter = Depends(get_storage),
) -> ResumeUploadResponse:
    """Validate, extract, store and persist one PDF without exposing its text."""
    try:
        filename = file.filename or ""
        if Path(filename).suffix.casefold() != ".pdf":
            raise _http_error(415, "UNSUPPORTED_FILE_EXTENSION", "Only PDF files are accepted.")
        if file.content_type != "application/pdf":
            raise _http_error(415, "UNSUPPORTED_MEDIA_TYPE", "Content-Type must be application/pdf.")

        chunks: list[bytes] = []
        total_bytes = 0
        header_prefix = bytearray()
        checksum = hashlib.sha256()
        while True:
            chunk = file.file.read(UPLOAD_CHUNK_SIZE_BYTES)
            if not chunk:
                break
            total_bytes += len(chunk)
            if total_bytes > MAX_UPLOAD_SIZE_BYTES:
                raise _http_error(413, "FILE_TOO_LARGE", f"The upload exceeds the {MAX_UPLOAD_SIZE_BYTES}-byte limit.")
            checksum.update(chunk)
            if len(header_prefix) < 1024:
                header_prefix.extend(chunk[: 1024 - len(header_prefix)])
            chunks.append(chunk)

        if total_bytes == 0:
            raise _http_error(400, "EMPTY_FILE", "The uploaded file is empty.")
        if b"%PDF-" not in header_prefix:
            raise _http_error(415, "INVALID_PDF_SIGNATURE", "The uploaded file does not have a valid PDF header.")

        pdf_bytes = b"".join(chunks)
        try:
            extraction = extract_pdf_bytes(pdf_bytes, MAX_PDF_PAGES)
        except PDFExtractionError as exc:
            status_code = 413 if exc.code == "PAGE_LIMIT_EXCEEDED" else 422
            raise _http_error(status_code, exc.code, exc.message) from exc

        try:
            result = ingest_resume(
                db=db,
                storage=storage,
                tenant_id=identity.tenant_id,
                actor_id=identity.actor_id,
                request_id=get_request_id(request),
                pdf_bytes=pdf_bytes,
                extraction=extraction,
                checksum=checksum.hexdigest(),
            )
        except ResumeDeletionPendingError as exc:
            raise _http_error(409, "RESUME_DELETION_PENDING", str(exc)) from exc
        resume = result.resume
        return ResumeUploadResponse(
            resume_id=UUID(resume.id),
            status="success",
            processing_status=resume.processing_status,
            duplicate=result.duplicate,
            file_size_bytes=resume.file_size_bytes,
            page_count=resume.page_count,
            char_count=resume.char_count,
        )
    except StorageError as exc:
        raise _http_error(503, "STORAGE_UNAVAILABLE", str(exc)) from exc
    finally:
        file.file.close()


@router.get("", response_model=ResumeListResponse)
def list_resumes(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    identity: RequestIdentity = Depends(get_identity),
    db: Session = Depends(get_db),
) -> ResumeListResponse:
    """List metadata for the active tenant; never returns page text or filename."""
    base_query = select(Resume).where(
        Resume.tenant_id == identity.tenant_id,
        Resume.processing_status != "DELETION_PENDING",
    )
    total = db.scalar(select(func.count()).select_from(base_query.subquery())) or 0
    records = db.scalars(
        base_query.order_by(Resume.created_at.desc(), Resume.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    db.add(AuditLog(
        tenant_id=identity.tenant_id,
        actor_id=identity.actor_id,
        action="RESUME_LISTED",
        resource_type="RESUME_COLLECTION",
        resource_id="00000000-0000-0000-0000-000000000000",
        request_id=get_request_id(request),
        metadata_json={"page": page, "page_size": page_size},
    ))
    db.commit()
    return ResumeListResponse(
        items=[ResumeMetadataResponse.model_validate(item) for item in records],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{resume_id}", response_model=ResumeMetadataResponse)
def get_resume(
    resume_id: UUID,
    request: Request,
    identity: RequestIdentity = Depends(get_identity),
    db: Session = Depends(get_db),
) -> ResumeMetadataResponse:
    """Return tenant-scoped metadata only; extracted page text stays private."""
    resume = db.scalar(_visible_resume_query(identity.tenant_id, resume_id))
    if resume is None:
        raise _http_error(404, "RESUME_NOT_FOUND", "Resume was not found.")
    db.add(AuditLog(
        tenant_id=identity.tenant_id,
        actor_id=identity.actor_id,
        action="RESUME_VIEWED",
        resource_type="RESUME",
        resource_id=resume.id,
        request_id=get_request_id(request),
        metadata_json={},
    ))
    db.commit()
    return ResumeMetadataResponse.model_validate(resume)


@router.delete("/{resume_id}", response_model=DeleteResponse)
def remove_resume(
    resume_id: UUID,
    request: Request,
    identity: RequestIdentity = Depends(get_identity),
    db: Session = Depends(get_db),
    storage: StorageAdapter = Depends(get_storage),
) -> DeleteResponse:
    """Delete a tenant-owned resume and all page metadata; retry if storage fails."""
    resume = db.scalar(_visible_resume_query(identity.tenant_id, resume_id))
    if resume is None:
        # Also permit a retry when a prior request committed DELETION_PENDING.
        resume = db.scalar(select(Resume).where(
            Resume.id == str(resume_id),
            Resume.tenant_id == identity.tenant_id,
            Resume.processing_status == "DELETION_PENDING",
        ))
    if resume is None:
        raise _http_error(404, "RESUME_NOT_FOUND", "Resume was not found.")
    try:
        delete_resume(
            db=db,
            storage=storage,
            tenant_id=identity.tenant_id,
            actor_id=identity.actor_id,
            request_id=get_request_id(request),
            resume=resume,
        )
    except StorageError as exc:
        raise _http_error(503, "STORAGE_DELETE_PENDING", "Resume deletion is pending storage cleanup; retry this request.") from exc
    return DeleteResponse(resume_id=resume_id, status="deleted")
