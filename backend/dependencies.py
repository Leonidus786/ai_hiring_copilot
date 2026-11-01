"""FastAPI dependencies for database, storage, and local development identity."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Generator

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from database import get_db as _get_db
from services.storage import LocalFilesystemStorage, StorageAdapter


@dataclass(frozen=True, slots=True)
class RequestIdentity:
    tenant_id: str
    actor_id: str


def get_db() -> Generator[Session, None, None]:
    yield from _get_db()


def get_storage() -> StorageAdapter:
    configured_path = os.getenv("RESUME_STORAGE_DIR")
    storage_root = Path(configured_path) if configured_path else Path(__file__).resolve().parent / "data" / "resumes"
    return LocalFilesystemStorage(storage_root)


def get_identity(
    x_tenant_id: uuid.UUID = Header(..., alias="X-Tenant-ID"),
    x_actor_id: uuid.UUID = Header(..., alias="X-Actor-ID"),
) -> RequestIdentity:
    """Local-only identity shim; not a production authentication mechanism.

    The UUID headers provide a testable tenant boundary for local development.
    They are caller-controlled and MUST be replaced by verified JWT/OIDC claims
    before exposing the service outside a trusted local environment.
    """
    app_env = os.getenv("APP_ENV", "production").casefold()
    if app_env != "development":
        raise HTTPException(
            status_code=503,
            detail={
                "error_code": "AUTH_PROVIDER_NOT_CONFIGURED",
                "message": "A verified production authentication provider is required.",
            },
        )
    return RequestIdentity(tenant_id=str(x_tenant_id), actor_id=str(x_actor_id))


def get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", str(uuid.uuid4()))


IdentityDependency = Depends(get_identity)
