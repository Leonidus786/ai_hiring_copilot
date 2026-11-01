# AI Hiring Copilot

An early-stage, recruiter-assistance application for parsing resumes, understanding job descriptions, and producing explainable, evidence-backed candidate-to-role insights. The system supports human review; it must not make autonomous hiring or rejection decisions.

> **Current project scope:** FastAPI backend with PDF ingestion, page-aware extraction, local persistence, tenant-scoped data queries, local document storage, and audit events. The frontend folder is currently empty. Structured LLM extraction, JD parsing, matching, skill-gap analysis, interview preparation, and learning plans remain planned work unless a later release report verifies them.

## Verified engineering status

| Capability | Status | Evidence / limitation |
|---|---|---|
| Windows Python 3.12 + `uv` environment | Tested | Fresh environment reproduced in the Git-connected checkout |
| FastAPI startup, Swagger, PDF upload | Tested | Local `POST /api/resume/upload` returned HTTP 200 |
| Batch 1 PDF validation and page extraction | Tested | 14 Windows tests passed before Batch 2 |
| Batch 2 database/storage implementation | Implemented in this patch | SQLite default, SQLAlchemy models, storage adapter, Alembic migration |
| Batch 2 automated tests | Tested in isolated build environment | 27 tests passed; rerun on the target Windows checkout before merging |
| PostgreSQL compatibility | Implemented, not integration-tested | SQLAlchemy + psycopg driver; no live PostgreSQL server test yet |
| Tenant data scoping | Implemented with development headers | Headers are caller-controlled and are NOT production authentication |
| OIDC/JWT authentication | Not implemented | Required before exposing service to users or the public internet |
| Structured resume extraction / Gemini or Groq integration | Not implemented | Provider adapter and deterministic fake belong to Phase 2 |
| JD parser / hybrid matching / skill gap engine | Planned | Not verified in current code |
| Interview question and learning-plan generation | Planned | Not verified in current code |
| Frontend | Missing | `frontend/` currently has no application files |
| Production deployment / load testing | Not verified | Local API tests do not establish production readiness |

Update this table only when new execution evidence exists.

## Architecture (current Phase 1)

```mermaid
flowchart TD
    C[Local API client] --> API[FastAPI]
    API --> ID[Development tenant/actor context]
    ID --> UP[Resume upload and lifecycle routes]
    UP --> VAL[Bounded PDF validation]
    VAL --> EXT[Page-aware pypdf extraction]
    EXT --> SVC[Resume ingestion service]
    SVC --> FS[(Private local PDF storage)]
    SVC --> DB[(SQLite local / PostgreSQL supported)]
    DB --> P[Resume metadata and per-page text]
    DB --> A[Audit events]
```

The development identity uses `X-Tenant-ID` and `X-Actor-ID` UUID headers so tenant scoping can be tested locally. These headers can be forged by a caller. They are **not authentication**. The app defaults to a fail-closed production mode; copy `backend/.env.example` to `backend/.env` to explicitly enable local development identity. Integrate verified JWT/OIDC claims before deployment.

## Windows CMD setup

From the repository root:

```cmd
cd /d E:\ai_hiring_copilot_github_check
uv venv --python 3.12 .venv
.venv\Scripts\activate.bat
uv pip install -r backend\requirements-dev.txt
```

Create the local environment file:

```cmd
copy backend\.env.example backend\.env
```

The defaults use a local SQLite database and a private local storage folder. Ensure `backend\data\` is ignored by Git; it contains candidate data and the local database.

## Database setup

For local development, `AUTO_CREATE_DB=true` creates missing tables at application startup. For migration-based setup (recommended for staging/production), set `AUTO_CREATE_DB=false` and run from the repository root:

```cmd
alembic -c alembic.ini upgrade head
```

Default local database: `backend/data/ai_hiring_copilot.db`.

To use PostgreSQL, configure a SQLAlchemy URL such as:

```text
postgresql+psycopg://USER:PASSWORD@HOST:5432/ai_hiring_copilot
```

The PostgreSQL driver is included, but a live PostgreSQL integration test has not yet been run. Store real credentials in `backend/.env` or a secret manager, never in Git.

## Run the API

```cmd
python -m uvicorn app:app --app-dir backend --reload
```

Open:

- http://127.0.0.1:8000/docs
- http://127.0.0.1:8000/health
- http://127.0.0.1:8000/ready

Stop with `CTRL+C`.

## Local API identity headers

For local development only, use stable UUIDs in Swagger's header fields:

```text
X-Tenant-ID: aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
X-Actor-ID: bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb
```

These identifiers are test context, not verified user identity. Do not deploy this header scheme as authentication.

## Current API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/resume/upload` | Validate, extract, store PDF and persist metadata/page text |
| GET | `/api/resume` | Tenant-scoped paginated metadata; no page text |
| GET | `/api/resume/{resume_id}` | Tenant-scoped metadata only |
| DELETE | `/api/resume/{resume_id}` | Retryable deletion of blob and database metadata |
| GET | `/health` | Liveness check |
| GET | `/ready` | Database `SELECT 1` and storage writability check |

Upload accepts PDF only, with a default 5 MiB byte limit and 20-page limit. Duplicate PDF content within the same tenant is idempotent by SHA-256 checksum. The same PDF uploaded in another tenant is stored as a separate record.

Successful upload response contains `resume_id`, processing status, duplicate flag, file size, page count, and character count. It does not return candidate text or original filename. Extracted page text is stored in the database for later evidence-grounded processing and must be protected as sensitive data.

## Tests

```cmd
python -m pytest backend\tests -q
```

Batch 2 test suite covers PDF validation, page boundaries, persistence, duplicate uploads, tenant query scoping, metadata-only responses, storage deletion, retryable deletion failures, path traversal rejection, and health/readiness endpoints. Offline tests use generated synthetic PDFs and SQLite.

## Data handling and security limitations

- Original PDF files are stored under `backend/data/resumes/<tenant-uuid>/<resume-uuid>.pdf` by default. The directory must remain private and excluded from Git.
- Extracted page text is stored in the database and can contain personal information. Do not use real candidate resumes in tests or demos without authorization.
- Audit events avoid storing raw filenames and resume text.
- The local filesystem adapter validates storage keys and performs atomic writes. An S3 adapter, encryption-at-rest configuration, backup policy, and retention scheduler are not implemented yet.
- Tenant scoping exists in application queries, but development UUID headers are spoofable. Verified authentication and role-based authorization are a release blocker for internet-facing deployment.
- Deletion is a two-step, retryable workflow because a filesystem and SQL database do not share one atomic transaction. A storage failure leaves the record in `DELETION_PENDING` for retry.
- Structured JSON logs, metrics/tracing, request-rate limits, malware scanning, and production secret management remain to be added.
- The system must assist human reviewers only. It must not automatically hire or reject candidates, and it must not use protected attributes or inferred proxies in matching.

## Roadmap

1. Complete and review Phase 1 secure ingestion acceptance on Windows and PostgreSQL.
2. Phase 2: provider-neutral structured resume extraction with strict Pydantic schemas, deterministic fake provider, page/quote evidence verification, bounded retries, and version history.
3. Phase 3: job-description parser with source evidence and prompt-injection boundaries.
4. Phase 4: explainable lexical/semantic matching, skill taxonomy, uncertainty states, and human review.
5. Phase 5: skill-gap analysis, interview questions with rubrics, and personalized learning plans.
6. Evaluation, fairness-risk review, CI, containerization, deployment, runbook, and frontend.

## License

No license is declared. Add one only after confirming the intended license and all included dependencies, models, and datasets' usage rights.
