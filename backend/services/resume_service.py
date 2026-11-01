"""Transactional application services for resume lifecycle operations."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models import AuditLog, Resume, ResumePage
from services.pdf_extractor import PDFExtractionResult
from services.storage import StorageAdapter


@dataclass(frozen=True, slots=True)
class IngestionResult:
    resume: Resume
    duplicate: bool


class ResumeDeletionPendingError(Exception):
    """A matching document exists but its previous deletion has not completed."""


def _audit(
    *, tenant_id: str, actor_id: str, action: str, resource_id: str,
    request_id: str, metadata: dict[str, object] | None = None,
) -> AuditLog:
    return AuditLog(
        tenant_id=tenant_id,
        actor_id=actor_id,
        action=action,
        resource_type="RESUME",
        resource_id=resource_id,
        request_id=request_id,
        metadata_json=metadata or {},
    )


def ingest_resume(
    *,
    db: Session,
    storage: StorageAdapter,
    tenant_id: str,
    actor_id: str,
    request_id: str,
    pdf_bytes: bytes,
    extraction: PDFExtractionResult,
    checksum: str,
) -> IngestionResult:
    """Persist a raw PDF and page-indexed text; clean up the blob on DB failure."""
    existing = db.scalar(
        select(Resume).where(
            Resume.tenant_id == tenant_id,
            Resume.sha256_checksum == checksum,
        )
    )
    if existing is not None:
        if existing.processing_status == "DELETION_PENDING":
            raise ResumeDeletionPendingError(
                "A previous deletion for this document is still pending. Retry deletion first."
            )
        db.add(_audit(
            tenant_id=tenant_id,
            actor_id=actor_id,
            action="RESUME_DUPLICATE_UPLOAD",
            resource_id=existing.id,
            request_id=request_id,
            metadata={"sha256_prefix": checksum[:12]},
        ))
        db.commit()
        return IngestionResult(resume=existing, duplicate=True)

    resume_id = str(uuid.uuid4())
    storage_key = storage.save(tenant_id, resume_id, pdf_bytes)
    resume = Resume(
        id=resume_id,
        tenant_id=tenant_id,
        uploaded_by=actor_id,
        storage_key=storage_key,
        sha256_checksum=checksum,
        file_size_bytes=len(pdf_bytes),
        page_count=extraction.page_count,
        char_count=extraction.char_count,
        parser_engine="pypdf",
        processing_status="EXTRACTED",
    )
    for page in extraction.pages:
        resume.pages.append(ResumePage(
            page_number=page.page_number,
            text_content=page.text,
            char_count=len(page.text),
        ))

    db.add(resume)
    db.add(_audit(
        tenant_id=tenant_id,
        actor_id=actor_id,
        action="RESUME_UPLOADED",
        resource_id=resume_id,
        request_id=request_id,
        metadata={
            "file_size_bytes": len(pdf_bytes),
            "page_count": extraction.page_count,
            "sha256_prefix": checksum[:12],
        },
    ))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        storage.delete(storage_key)
        # A concurrent identical upload may have committed after our first lookup.
        concurrent_duplicate = db.scalar(
            select(Resume).where(
                Resume.tenant_id == tenant_id,
                Resume.sha256_checksum == checksum,
            )
        )
        if concurrent_duplicate is not None:
            if concurrent_duplicate.processing_status == "DELETION_PENDING":
                raise ResumeDeletionPendingError(
                    "A previous deletion for this document is still pending. Retry deletion first."
                )
            return IngestionResult(resume=concurrent_duplicate, duplicate=True)
        raise
    except Exception:
        db.rollback()
        storage.delete(storage_key)
        raise

    return IngestionResult(resume=resume, duplicate=False)


def delete_resume(
    *, db: Session, storage: StorageAdapter, tenant_id: str, actor_id: str,
    request_id: str, resume: Resume,
) -> None:
    """Delete blob and metadata with a retryable DELETION_PENDING state.

    File storage and SQL databases do not share a transaction. The first DB
    commit records intent. Storage deletion is idempotent. A final DB transaction
    deletes metadata. If storage fails, metadata remains pending for a safe retry.
    """
    if resume.processing_status != "DELETION_PENDING":
        resume.processing_status = "DELETION_PENDING"
        db.add(_audit(
            tenant_id=tenant_id,
            actor_id=actor_id,
            action="RESUME_DELETION_REQUESTED",
            resource_id=resume.id,
            request_id=request_id,
        ))
        db.commit()

    storage.delete(resume.storage_key)

    resume_id = resume.id
    db.delete(resume)
    db.add(_audit(
        tenant_id=tenant_id,
        actor_id=actor_id,
        action="RESUME_DELETED",
        resource_id=resume_id,
        request_id=request_id,
    ))
    db.commit()
