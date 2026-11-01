from __future__ import annotations

import sys
from pathlib import Path
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


@pytest.fixture()
def test_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[dict[str, object], None, None]:
    """Run the real FastAPI app against an isolated SQLite DB and temp storage."""
    from database import Base
    from dependencies import get_db, get_storage
    from services.storage import LocalFilesystemStorage
    import app as app_module

    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("AUTO_CREATE_DB", "true")
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(test_engine)
    TestSessionLocal = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
    storage = LocalFilesystemStorage(tmp_path / "private-resume-storage")

    def override_get_db():
        session = TestSessionLocal()
        try:
            yield session
        finally:
            session.close()

    monkeypatch.setattr(app_module, "engine", test_engine)
    app_module.app.dependency_overrides[get_db] = override_get_db
    app_module.app.dependency_overrides[get_storage] = lambda: storage

    headers = {
        "X-Tenant-ID": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "X-Actor-ID": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
    }
    try:
        with TestClient(app_module.app, headers=headers) as test_client:
            yield {
                "client": test_client,
                "engine": test_engine,
                "session_factory": TestSessionLocal,
                "storage": storage,
                "headers": headers,
                "tmp_path": tmp_path,
            }
    finally:
        app_module.app.dependency_overrides.clear()
        test_engine.dispose()


@pytest.fixture()
def client(test_context: dict[str, object]) -> TestClient:
    return test_context["client"]
