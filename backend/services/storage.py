"""Private local filesystem storage adapter for uploaded resume documents."""

from __future__ import annotations

import os
import uuid
from pathlib import Path, PurePosixPath
from typing import Protocol


class StorageError(Exception):
    """Raised when a storage operation fails."""


class StorageAdapter(Protocol):
    def save(self, tenant_id: str, resume_id: str, content: bytes) -> str: ...
    def delete(self, storage_key: str) -> None: ...
    def health_check(self) -> bool: ...


class LocalFilesystemStorage:
    """Store opaque PDF objects below a configured private directory."""

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve_key(self, storage_key: str) -> Path:
        key = PurePosixPath(storage_key)
        if key.is_absolute() or len(key.parts) != 2 or any(part in {"", ".", ".."} for part in key.parts):
            raise StorageError("Invalid storage key.")
        if not key.parts[0] or not key.parts[1].endswith(".pdf"):
            raise StorageError("Invalid storage key.")
        candidate = (self.root / Path(*key.parts)).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise StorageError("Storage key escapes the configured root.") from exc
        return candidate

    def save(self, tenant_id: str, resume_id: str, content: bytes) -> str:
        try:
            tenant_uuid = str(uuid.UUID(tenant_id))
            resume_uuid = str(uuid.UUID(resume_id))
            if not content:
                raise StorageError("Cannot store an empty document.")
            storage_key = f"{tenant_uuid}/{resume_uuid}.pdf"
            destination = self._resolve_key(storage_key)
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_name(f".{resume_uuid}.{uuid.uuid4().hex}.tmp")
            try:
                with temporary.open("xb") as output:
                    output.write(content)
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary, destination)
            finally:
                if temporary.exists():
                    temporary.unlink()
            return storage_key
        except StorageError:
            raise
        except (OSError, ValueError) as exc:
            raise StorageError("The resume document could not be stored.") from exc

    def delete(self, storage_key: str) -> None:
        try:
            target = self._resolve_key(storage_key)
            target.unlink(missing_ok=True)
            try:
                target.parent.rmdir()
            except OSError:
                # The tenant directory may contain other resumes; keep it.
                pass
        except StorageError:
            raise
        except OSError as exc:
            raise StorageError("The resume document could not be deleted.") from exc

    def health_check(self) -> bool:
        probe = self.root / f".health-{uuid.uuid4().hex}.tmp"
        try:
            with probe.open("xb") as output:
                output.write(b"ok")
                output.flush()
                os.fsync(output.fileno())
            return True
        except OSError as exc:
            raise StorageError("Resume storage is not writable.") from exc
        finally:
            probe.unlink(missing_ok=True)
