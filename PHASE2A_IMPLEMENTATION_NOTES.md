# Phase 2A Patch — Structured Resume Intelligence Foundation

Copy the `backend\extraction` package, the new test file, and the acceptance note into the Git-connected repository. No existing file is overwritten by this patch.

The batch introduces strict Pydantic candidate-profile contracts, a provider protocol, a deterministic offline fake provider, and page-scoped exact quote verification. It intentionally does not integrate a live Gemini/Groq adapter or modify the API/database yet.

See `docs\PHASE2A_ACCEPTANCE.md` for scope, semantics, limitations, and CMD test instructions.
