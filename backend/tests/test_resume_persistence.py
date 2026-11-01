from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from sqlalchemy import select, func

from dependencies import get_storage
from models import AuditLog, Resume, ResumePage
from services.storage import StorageError
from io import BytesIO
from reportlab.pdfgen import canvas


def make_text_pdf(*page_texts: str) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    for page_text in page_texts:
        pdf.drawString(72, 720, page_text)
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()

TENANT_B = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
ACTOR_B = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"


def upload(client, content: bytes, filename: str = "synthetic.pdf"):
    return client.post(
        "/api/resume/upload",
        files={"file": (filename, content, "application/pdf")},
    )


def test_resume_is_persisted_and_listed_without_page_text(client, test_context):
    content = make_text_pdf("Synthetic candidate: Python, FastAPI", "Synthetic project: PostgreSQL")
    response = upload(client, content)
    assert response.status_code == 200
    resume_id = response.json()["resume_id"]

    listed = client.get("/api/resume")
    assert listed.status_code == 200
    body = listed.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == resume_id
    assert "text_content" not in listed.text
    assert "Synthetic candidate" not in listed.text

    session_factory = test_context["session_factory"]
    with session_factory() as session:
        record = session.get(Resume, resume_id)
        assert record is not None
        assert record.page_count == 2
        assert record.char_count > 0
        pages = session.scalars(select(ResumePage).where(ResumePage.resume_id == resume_id).order_by(ResumePage.page_number)).all()
        assert [page.page_number for page in pages] == [1, 2]
        assert "Synthetic candidate" in pages[0].text_content

    storage_root = test_context["tmp_path"] / "private-resume-storage"
    assert list(storage_root.rglob("*.pdf"))


def test_duplicate_upload_is_idempotent_within_tenant(client, test_context):
    content = make_text_pdf("Same synthetic resume")
    first = upload(client, content)
    second = upload(client, content)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["resume_id"] == second.json()["resume_id"]
    assert second.json()["duplicate"] is True

    session_factory = test_context["session_factory"]
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Resume)) == 1
        assert session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "RESUME_DUPLICATE_UPLOAD")) == 1


def test_same_file_in_different_tenants_is_not_a_duplicate(client):
    content = make_text_pdf("Tenant-scoped duplicate test")
    first = upload(client, content)
    second = client.post(
        "/api/resume/upload",
        headers={"X-Tenant-ID": TENANT_B, "X-Actor-ID": ACTOR_B},
        files={"file": ("synthetic.pdf", content, "application/pdf")},
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["resume_id"] != second.json()["resume_id"]
    assert second.json()["duplicate"] is False


def test_cross_tenant_get_and_delete_return_not_found(client):
    response = upload(client, make_text_pdf("Private tenant data"))
    resume_id = response.json()["resume_id"]
    other_headers = {"X-Tenant-ID": TENANT_B, "X-Actor-ID": ACTOR_B}
    get_response = client.get(f"/api/resume/{resume_id}", headers=other_headers)
    delete_response = client.delete(f"/api/resume/{resume_id}", headers=other_headers)
    assert get_response.status_code == 404
    assert delete_response.status_code == 404


def test_missing_identity_headers_are_rejected(client):
    response = client.get(
        "/api/resume",
        headers={"X-Tenant-ID": "", "X-Actor-ID": "", "X-Request-ID": "missing-header-check"},
    )
    assert response.status_code == 422
    assert response.json()["request_id"] == "missing-header-check"


def test_detail_returns_metadata_only_and_records_view_audit(client, test_context):
    response = upload(client, make_text_pdf("Candidate PII must not be in response"))
    resume_id = response.json()["resume_id"]
    detail = client.get(f"/api/resume/{resume_id}")
    assert detail.status_code == 200
    assert "Candidate PII" not in detail.text
    assert "storage_key" not in detail.json()
    session_factory = test_context["session_factory"]
    with session_factory() as session:
        actions = session.scalars(select(AuditLog.action)).all()
    assert "RESUME_VIEWED" in actions


def test_delete_removes_blob_and_metadata_but_retains_audit(client, test_context):
    response = upload(client, make_text_pdf("Delete me safely"))
    resume_id = response.json()["resume_id"]
    storage_root: Path = test_context["tmp_path"] / "private-resume-storage"
    assert list(storage_root.rglob("*.pdf"))

    deleted = client.delete(f"/api/resume/{resume_id}")
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "deleted"
    assert not list(storage_root.rglob("*.pdf"))

    session_factory = test_context["session_factory"]
    with session_factory() as session:
        assert session.get(Resume, resume_id) is None
        assert session.scalar(select(func.count()).select_from(ResumePage).where(ResumePage.resume_id == resume_id)) == 0
        actions = session.scalars(select(AuditLog.action).where(AuditLog.resource_id == resume_id)).all()
    assert "RESUME_DELETED" in actions
    assert client.get(f"/api/resume/{resume_id}").status_code == 404


def test_storage_delete_failure_keeps_retryable_pending_record(client, test_context):
    content = make_text_pdf("Retry deletion")
    response = upload(client, content)
    resume_id = response.json()["resume_id"]
    real_storage = test_context["storage"]

    class FailingDeleteStorage:
        def save(self, tenant_id: str, resume_id: str, content: bytes) -> str:
            return real_storage.save(tenant_id, resume_id, content)
        def delete(self, storage_key: str) -> None:
            raise StorageError("simulated storage outage")
        def health_check(self) -> bool:
            return True

    client.app.dependency_overrides[get_storage] = lambda: FailingDeleteStorage()
    first_delete = client.delete(f"/api/resume/{resume_id}")
    assert first_delete.status_code == 503

    session_factory = test_context["session_factory"]
    with session_factory() as session:
        record = session.get(Resume, resume_id)
        assert record is not None
        assert record.processing_status == "DELETION_PENDING"

    blocked_duplicate = upload(client, content)
    assert blocked_duplicate.status_code == 409
    assert blocked_duplicate.json()["detail"]["error_code"] == "RESUME_DELETION_PENDING"

    client.app.dependency_overrides[get_storage] = lambda: real_storage
    retry_delete = client.delete(f"/api/resume/{resume_id}")
    assert retry_delete.status_code == 200
    with session_factory() as session:
        assert session.get(Resume, resume_id) is None


def test_health_and_readiness_endpoints(client):
    assert client.get("/health").json() == {"status": "ok"}
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_local_storage_rejects_path_traversal(test_context):
    storage = test_context["storage"]
    try:
        storage.delete("../../outside.pdf")
    except StorageError:
        pass
    else:
        raise AssertionError("Path traversal storage key was not rejected")


def test_production_mode_fails_closed_without_auth_provider(client, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    response = client.get("/api/resume")
    assert response.status_code == 503
    assert response.json()["detail"]["error_code"] == "AUTH_PROVIDER_NOT_CONFIGURED"
    monkeypatch.setenv("APP_ENV", "development")


def test_list_is_tenant_scoped_and_page_size_is_bounded(client):
    first_content = make_text_pdf("Tenant A resume one")
    second_content = make_text_pdf("Tenant A resume two")
    assert upload(client, first_content).status_code == 200
    assert upload(client, second_content).status_code == 200

    tenant_b_response = client.post(
        "/api/resume/upload",
        headers={"X-Tenant-ID": TENANT_B, "X-Actor-ID": ACTOR_B},
        files={"file": ("tenant-b.pdf", make_text_pdf("Tenant B only"), "application/pdf")},
    )
    assert tenant_b_response.status_code == 200

    tenant_a_list = client.get("/api/resume?page=1&page_size=1")
    tenant_b_list = client.get(
        "/api/resume",
        headers={"X-Tenant-ID": TENANT_B, "X-Actor-ID": ACTOR_B},
    )
    assert tenant_a_list.json()["total"] == 2
    assert len(tenant_a_list.json()["items"]) == 1
    assert tenant_b_list.json()["total"] == 1

    invalid_page_size = client.get("/api/resume?page_size=101")
    assert invalid_page_size.status_code == 422


def test_storage_write_failure_returns_service_unavailable(client, test_context):
    class FailingSaveStorage:
        def save(self, tenant_id: str, resume_id: str, content: bytes) -> str:
            raise StorageError("simulated storage write outage")
        def delete(self, storage_key: str) -> None:
            return None
        def health_check(self) -> bool:
            return False

    client.app.dependency_overrides[get_storage] = lambda: FailingSaveStorage()
    response = upload(client, make_text_pdf("Storage failure test"))
    assert response.status_code == 503
    assert response.json()["detail"]["error_code"] == "STORAGE_UNAVAILABLE"

    session_factory = test_context["session_factory"]
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Resume)) == 0
