# Phase 2A — Structured Resume Intelligence Foundation

## Scope

This batch adds provider-neutral candidate-profile schemas, a deterministic offline provider, input bounds, and strict source-quote presence verification. It does not call Gemini/Groq, create an API endpoint, or persist extraction versions.

## Files

- `backend/extraction/schemas.py` — strict Pydantic domain contracts, separate from HTTP DTOs in `backend/schemas.py`.
- `backend/extraction/providers.py` — provider protocol and deterministic rule-based fake.
- `backend/extraction/evidence.py` — page-scoped verbatim quote presence checks.
- `backend/extraction/service.py` — input bounds, schema validation, provider boundary, and evidence verification.
- `backend/tests/test_resume_extraction.py` — offline tests.

## Important semantics

- Every non-null contact value must carry a source quote.
- Every skill, work-history item, project, education record, and certification must carry one or more source quotes. A non-null skill proficiency needs separate supporting evidence.
- A source quote must occur on the declared page after whitespace normalization.
- Quote presence does **not** prove semantic support for every field in a record. That requires separate evaluation and reviewer confirmation.
- Missing values remain null/empty; years of experience, proficiency, or skills are not inferred by this batch.
- The fake provider recognizes only explicit `Name:` / `Candidate:` and `Skills:` lines. It is a test adapter, not an AI model.
- Provider errors are sanitized at the service boundary; raw resume text and provider payloads are not included in exception messages.

## Not included

- Gemini/Groq network adapters and API key configuration.
- Database persistence of extracted profiles or extraction versions.
- Human correction endpoints.
- JD parsing and candidate-role matching.
- Production authentication, encryption, or fairness validation.

## Run tests (Windows CMD)

```cmd
set PYTHONPATH=%CD%\backend
python -m pytest backend\tests -q
```

## Acceptance

The new tests must pass on the target Windows Python environment. The full suite must be rerun. Live provider calls are not required for this batch.
