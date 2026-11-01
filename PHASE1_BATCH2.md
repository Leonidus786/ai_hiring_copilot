# AI Hiring Copilot — Phase 1, Batch 2

## Scope

Adds local persistence and a storage lifecycle to the Batch 1 PDF ingestion implementation. Existing `/api/resume/upload` path is preserved.

### Included

- SQLAlchemy models for `resumes`, `resume_pages`, and `audit_logs`.
- Local SQLite default and PostgreSQL URL/driver support.
- Alembic initial migration.
- Local filesystem storage adapter with UUID-based storage keys, atomic writes, and path traversal checks.
- SHA-256 idempotency scoped by tenant.
- Local-only UUID headers (`X-Tenant-ID`, `X-Actor-ID`) and tenant-scoped reads/deletes.
- `GET /api/resume`, `GET /api/resume/{id}`, and `DELETE /api/resume/{id}`.
- Audit events for upload, duplicate upload, list, view, delete request, and delete completion.
- `GET /health`, `GET /ready`, and request correlation ID response headers.
- Synthetic offline tests.

### Explicitly not included

- Real OIDC/JWT authentication or production RBAC.
- Live PostgreSQL integration verification.
- S3/object storage implementation, encryption-at-rest, backups, retention scheduler.
- Structured JSON logging/metrics/tracing.
- LLM extraction, JD parsing, matching, frontend, or deployment.

## Local development identity warning

The UUID identity headers are only a local test boundary. A caller can choose any UUID, so this is not authentication. The app returns `AUTH_PROVIDER_NOT_CONFIGURED` when `APP_ENV` is not `development`. Do not change that guard or expose this API publicly until verified JWT/OIDC authentication is integrated.

## Apply to the Git-connected checkout

Assumes the primary checkout is `E:\ai_hiring_copilot_github_check` and this patch folder is `C:\Users\sniti\Downloads\ai_hiring_copilot_phase1_batch2`.

1. Stop Uvicorn with `CTRL+C`.
2. Confirm Git working tree is clean and create a checkpoint branch or commit before applying.
3. Back up files being replaced.
4. Copy the files from the patch folder, preserving the existing `backend/routes/__init__.py` and `backend/services/__init__.py` if present (the patch includes empty package markers).
5. Install updated dependencies, run tests, and run the Alembic migration against a disposable local database before starting the API.

Recommended CMD commands are supplied in the assistant's implementation handoff. Do not copy the `backend/data` directory from another machine.

## Verification acceptance

- All Batch 1 tests remain green.
- Upload persists PDF blob, checksum, metadata, and one page-text row per extracted page.
- Re-upload of identical bytes in same tenant returns the existing ID and does not create a second resume.
- Same bytes in another tenant create a different tenant-scoped record.
- Cross-tenant detail/delete return 404.
- Listing/detail do not return stored page text or original filename.
- Delete removes blob, resume, and page text while preserving audit records.
- Storage deletion failure leaves `DELETION_PENDING`; retry completes cleanup.
- Readiness verifies DB and storage.
- Alembic upgrade/downgrade succeeds on SQLite.

## Red-team notes

1. **Critical deployment limitation:** local identity headers are spoofable; production authentication is not implemented. The API must not be internet-facing until OIDC/JWT and authorization are added.
2. **Sensitive data at rest:** resume page text and PDF are locally stored without application-layer encryption. Protect the host volume and use encrypted storage/managed keys in production.
3. **Cross-resource deletion:** file and SQL database cannot share one transaction. The `DELETION_PENDING` state makes storage cleanup retryable; operators must monitor pending records.
4. **PostgreSQL:** dialect/driver compatibility is implemented but not yet validated against a live PostgreSQL server.
5. **Scale:** upload bytes are bounded to 5 MiB; in-memory parsing and synchronous persistence are appropriate only for this bounded local MVP. Load testing is still required.
