"""Database engine and session management for AI Hiring Copilot."""

from __future__ import annotations

import os
from pathlib import Path
from collections.abc import Generator

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

BACKEND_DIR = Path(__file__).resolve().parent
DEFAULT_DATA_DIR = BACKEND_DIR / "data"
DEFAULT_DATA_DIR.mkdir(parents=True, exist_ok=True)
load_dotenv(BACKEND_DIR / ".env")
DEFAULT_DATABASE_PATH = DEFAULT_DATA_DIR / "ai_hiring_copilot.db"
DEFAULT_DATABASE_URL = f"sqlite:///{DEFAULT_DATABASE_PATH.as_posix()}"


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""


def build_engine(database_url: str | None = None) -> Engine:
    """Build a database engine for SQLite or PostgreSQL."""
    url = database_url or os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args, pool_pre_ping=True)


engine = build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """Yield one SQLAlchemy session per request."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
