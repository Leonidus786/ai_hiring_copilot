"""FastAPI application entry point."""

from __future__ import annotations

import os
import re
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import Base, engine
from dependencies import get_db, get_storage
from routes.resume import router as resume_router
from services.storage import StorageAdapter


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Create local development tables; production must run Alembic migrations."""
    auto_create = os.getenv("AUTO_CREATE_DB", "false").casefold() in {"1", "true", "yes"}
    if auto_create:
        Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="AI Hiring Copilot", version="1.1.0", lifespan=lifespan)
origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-Tenant-ID", "X-Actor-ID", "X-Request-ID"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    supplied = request.headers.get("X-Request-ID", "")
    request_id = supplied if re.fullmatch(r"[A-Za-z0-9._:-]{1,64}", supplied) else str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(HTTPException)
async def http_exception_with_request_id(request: Request, exc: HTTPException):
    """Attach the correlation ID to controlled HTTP error responses."""
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    if isinstance(exc.detail, dict):
        detail = {**exc.detail, "request_id": request_id}
    else:
        detail = {"message": str(exc.detail), "request_id": request_id}
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": detail},
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_error_with_request_id(request: Request, exc: RequestValidationError):
    """Attach correlation IDs to FastAPI request-validation responses."""
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    return JSONResponse(
        status_code=422,
        content={"detail": jsonable_encoder(exc.errors()), "request_id": request_id},
    )


app.include_router(resume_router, prefix="/api/resume", tags=["Resume"])


@app.get("/")
def root() -> dict[str, str]:
    return {"status": "AI Hiring Copilot is running", "version": app.version}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
def ready(
    db: Session = Depends(get_db),
    storage: StorageAdapter = Depends(get_storage),
) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
        storage.health_check()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database or storage is not ready.") from exc
    return {"status": "ready"}
