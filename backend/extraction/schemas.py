"""Strict Pydantic contracts for evidence-backed resume extraction.

These are domain schemas, deliberately separate from ``backend/schemas.py``,
which contains public HTTP response DTOs for the resume lifecycle API.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


SkillCategory = Literal[
    "programming_language",
    "framework",
    "library",
    "database",
    "cloud_platform",
    "tool",
    "methodology",
    "domain_knowledge",
    "other",
]

ProficiencyLevel = Literal["beginner", "intermediate", "advanced", "expert"]


class StrictSchema(BaseModel):
    """Base class that rejects unexpected keys and strips surrounding whitespace."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ResumeSourcePage(StrictSchema):
    """One page of text that was already extracted from an uploaded document."""

    page_number: int = Field(ge=1)
    text: str = Field(min_length=1, max_length=200_000)


class SourceEvidence(StrictSchema):
    """A verbatim source quote and its one-based PDF page number."""

    page_number: int = Field(ge=1)
    quote: str = Field(min_length=3, max_length=1_000)


class EvidenceBackedValue(StrictSchema):
    """A single extracted value; a non-null value must cite source evidence."""

    value: str | None = Field(default=None, min_length=1, max_length=500)
    evidence: SourceEvidence | None = None

    @model_validator(mode="after")
    def value_requires_evidence(self) -> "EvidenceBackedValue":
        if self.value is not None and self.evidence is None:
            raise ValueError("A populated value requires source evidence.")
        if self.value is None and self.evidence is not None:
            raise ValueError("Evidence cannot be attached to an unknown value.")
        return self


class SkillClaim(StrictSchema):
    name: str = Field(min_length=1, max_length=120)
    category: SkillCategory = "other"
    proficiency: ProficiencyLevel | None = None
    evidence: list[SourceEvidence] = Field(min_length=1, max_length=5)
    proficiency_evidence: list[SourceEvidence] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def proficiency_requires_its_own_evidence(self) -> "SkillClaim":
        if self.proficiency is not None and not self.proficiency_evidence:
            raise ValueError("A proficiency level requires separate supporting evidence.")
        if self.proficiency is None and self.proficiency_evidence:
            raise ValueError("Proficiency evidence cannot be attached when proficiency is unknown.")
        return self


class WorkExperience(StrictSchema):
    role: str | None = Field(default=None, max_length=200)
    organization: str | None = Field(default=None, max_length=200)
    start_date_raw: str | None = Field(default=None, max_length=80)
    end_date_raw: str | None = Field(default=None, max_length=80)
    responsibilities: list[str] = Field(default_factory=list, max_length=20)
    evidence: list[SourceEvidence] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def requires_at_least_one_claim(self) -> "WorkExperience":
        if not any((self.role, self.organization, self.start_date_raw, self.end_date_raw, self.responsibilities)):
            raise ValueError("A work-history item must contain at least one extracted claim.")
        return self


class ProjectExperience(StrictSchema):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2_000)
    technologies: list[str] = Field(default_factory=list, max_length=30)
    evidence: list[SourceEvidence] = Field(min_length=1, max_length=8)


class EducationRecord(StrictSchema):
    qualification: str | None = Field(default=None, max_length=200)
    institution: str | None = Field(default=None, max_length=200)
    field_of_study: str | None = Field(default=None, max_length=200)
    completion_date_raw: str | None = Field(default=None, max_length=80)
    evidence: list[SourceEvidence] = Field(min_length=1, max_length=5)

    @model_validator(mode="after")
    def requires_at_least_one_claim(self) -> "EducationRecord":
        if not any((self.qualification, self.institution, self.field_of_study, self.completion_date_raw)):
            raise ValueError("An education item must contain at least one extracted claim.")
        return self


class CertificationRecord(StrictSchema):
    name: str = Field(min_length=1, max_length=200)
    issuer: str | None = Field(default=None, max_length=200)
    issue_date_raw: str | None = Field(default=None, max_length=80)
    evidence: list[SourceEvidence] = Field(min_length=1, max_length=5)


class CandidateProfile(StrictSchema):
    """Structured candidate facts; no inferred overall experience or fit score."""

    schema_version: Literal["1.0"] = "1.0"
    full_name: EvidenceBackedValue | None = None
    email: EvidenceBackedValue | None = None
    phone: EvidenceBackedValue | None = None
    skills: list[SkillClaim] = Field(default_factory=list, max_length=200)
    work_experience: list[WorkExperience] = Field(default_factory=list, max_length=50)
    projects: list[ProjectExperience] = Field(default_factory=list, max_length=100)
    education: list[EducationRecord] = Field(default_factory=list, max_length=30)
    certifications: list[CertificationRecord] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def skill_names_are_unique(self) -> "CandidateProfile":
        normalized_names = [skill.name.casefold() for skill in self.skills]
        if len(normalized_names) != len(set(normalized_names)):
            raise ValueError("Duplicate skill names are not allowed; normalize before validation.")
        return self
