"""Explicit API response schemas. Sensitive page text is never exposed here."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ResumeMetadataResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    processing_status: str
    file_size_bytes: int = Field(ge=0)
    page_count: int = Field(ge=1)
    char_count: int = Field(ge=1)
    created_at: datetime


class ResumeUploadResponse(BaseModel):
    resume_id: UUID
    status: str
    processing_status: str
    duplicate: bool
    file_size_bytes: int
    page_count: int
    char_count: int


class ResumeListResponse(BaseModel):
    items: list[ResumeMetadataResponse]
    total: int
    page: int
    page_size: int


class DeleteResponse(BaseModel):
    resume_id: UUID
    status: str
