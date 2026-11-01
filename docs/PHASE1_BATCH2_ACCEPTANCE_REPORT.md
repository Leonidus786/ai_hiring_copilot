# Phase 1 — Batch 2: Persistence & Storage Acceptance Report

**Patch validation environment:** Linux container, Python 3.13.5; FastAPI 0.128.2; SQLAlchemy 2.0.50; Alembic 1.18.4; pypdf 5.9.0; pytest 9.0.2; httpx 0.28.1; ReportLab 4.4.9.

This is isolated patch validation, not evidence from the user's Windows PC or live PostgreSQL server.

## Implemented in this patch

- SQLAlchemy models: `resumes`, `resume_pages`, `audit_logs`.
- SQLite local default; PostgreSQL SQLAlchemy URL support and psycopg v3 driver dependency.
- Alembic initial migration.
- Local storage adapter with UUID-only storage keys, atomic writes, path containment checks, and health probe.
- SHA-256 checksum and same-tenant idempotent upload handling.
- Development-only tenant/actor UUID headers; fail-closed response outside development mode.
- Tenant-scoped listing, detail, and deletion.
- PII-minimized API responses; stored page text is not included in list/detail responses.
- Request ID response header and request ID in controlled HTTP/validation errors.
- Retryable deletion state when filesystem deletion fails.
- `GET /health` and `GET /ready`.

## Commands executed and actual results

| Command / check | Result |
|---|---|
| `PYTHONPATH=... pytest -q backend/tests` | **27 passed** |
| `python -m compileall -q backend` | Passed; no syntax errors |
| `alembic upgrade head` against disposable SQLite DB | Passed |
| `alembic check` against migrated disposable SQLite DB | `No new upgrade operations detected.` |
| `alembic downgrade base` against disposable SQLite DB | Passed |
| Ruff lint | NOT RUN; ruff was unavailable and package index DNS was unavailable in the isolated environment |
| Live PostgreSQL integration | NOT RUN; no PostgreSQL server was available |
| Windows Python 3.12 verification | NOT RUN; user must execute after applying patch |

## Test coverage by behavior

- Original PDF validation and page extraction tests retained.
- Upload route metadata-only response.
- Upload validation: extension, media type, signature, blank/scanned-like textless PDF, file-size and page limits, encrypted PDF.
- Persistence of raw blob, resume metadata, and page-indexed text.
- Duplicate upload idempotency per tenant.
- Same bytes accepted as a separate document in another tenant.
- Cross-tenant detail/delete isolation.
- Required local identity headers.
- Detail/list do not return page text.
- Audit events for views and deletion.
- Blob and page/metadata deletion.
- Retryable `DELETION_PENDING` behavior on storage outage.
- Path traversal rejection.
- Liveness/readiness checks.
- Production mode fails closed without an auth provider.
- Storage write failure response.
- Tenant-scoped pagination and page-size validation.

## Remaining blockers before Phase 1 can be called complete

1. Replace local development UUID headers with verified JWT/OIDC authentication and authorization before deployment.
2. Validate the PostgreSQL path against a live server and run migration + API integration tests.
3. Add structured JSON logs with guaranteed PII redaction; request IDs are implemented, full structured logging is not.
4. Add at-rest encryption, backup/restore, retention, and deletion operations for production storage.
5. Consider malware scanning and stronger PDF parser resource isolation before accepting untrusted public uploads.
6. Verify all behavior on the user's Windows Python 3.12 environment.
7. Add CI, formatting/type checks, and security/dependency checks.
8. The current PDF extraction uses pypdf only; the earlier broader specification's pdfplumber + controlled fallback is not implemented.

## Red-team review

- **Critical:** `X-Tenant-ID`/`X-Actor-ID` are spoofable development headers. `APP_ENV` defaults to production; local headers work only after explicitly setting `APP_ENV=development` in `backend/.env`. Do not expose development mode publicly.
- **High:** page text and raw PDFs contain personal information and are not application-encrypted in this local adapter.
- **High:** filesystem and DB are not one transaction. The two-step `DELETION_PENDING` protocol enables retry, but pending deletions require operational monitoring.
- **Medium:** upload body remains bounded in memory to 5 MiB; this is a bounded MVP design, not proof of high-concurrency capacity.
- **Medium:** Alembic SQLite migration is tested; PostgreSQL behavior is not yet exercised.
- **Medium:** audit records are append-only by application convention, not cryptographically tamper-proof or protected by database permissions/triggers.

## Next acceptance gate

On Windows, apply the patch to the Git-connected checkout, install the updated backend requirements, run all 27 tests, start FastAPI, verify `/health`, `/ready`, upload/list/detail/delete using synthetic PDFs and the local UUID headers, then inspect `git diff` before committing.
