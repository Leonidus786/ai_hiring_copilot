"""Provider-neutral orchestration for schema and evidence validation."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Mapping

from pydantic import ValidationError

from .evidence import EvidenceValidationError, verify_profile_evidence
from .providers import ResumeExtractionProvider
from .schemas import CandidateProfile, ResumeSourcePage

MAX_SOURCE_PAGES = 20
MAX_SOURCE_CHARACTERS = 200_000


class ExtractionInputError(Exception):
    """The supplied source pages violate input limits or basic invariants."""


class ResumeProfileValidationError(Exception):
    """Provider output does not satisfy the candidate profile contract."""


class ExtractionProviderError(Exception):
    """Provider failed; message intentionally excludes provider payloads."""


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    profile: CandidateProfile
    provider_name: str
    model_name: str
    schema_version: str
    evidence_verified: bool


class ResumeExtractionService:
    """Validate source bounds, provider output and source-quote presence."""

    def __init__(self, provider: ResumeExtractionProvider) -> None:
        self._provider = provider

    def extract(self, pages: Sequence[ResumeSourcePage]) -> ExtractionResult:
        normalized_pages = tuple(sorted(pages, key=lambda page: page.page_number))
        if not normalized_pages:
            raise ExtractionInputError("At least one source page is required.")
        if len(normalized_pages) > MAX_SOURCE_PAGES:
            raise ExtractionInputError("The source exceeds the maximum page count.")

        page_numbers = [page.page_number for page in normalized_pages]
        if len(page_numbers) != len(set(page_numbers)):
            raise ExtractionInputError("Source page numbers must be unique.")

        total_characters = sum(len(page.text) for page in normalized_pages)
        if total_characters > MAX_SOURCE_CHARACTERS:
            raise ExtractionInputError("The source exceeds the maximum text size.")

        try:
            raw_profile = self._provider.extract(normalized_pages)
        except Exception as exc:  # provider-specific failures are sanitized at this boundary
            raise ExtractionProviderError("The resume extraction provider failed.") from exc

        try:
            profile = (
                raw_profile
                if isinstance(raw_profile, CandidateProfile)
                else CandidateProfile.model_validate(raw_profile)
            )
        except (ValidationError, TypeError, ValueError) as exc:
            raise ResumeProfileValidationError(
                "The provider response did not satisfy the candidate profile schema."
            ) from exc

        verify_profile_evidence(profile, normalized_pages)

        return ExtractionResult(
            profile=profile,
            provider_name=self._provider.provider_name,
            model_name=self._provider.model_name,
            schema_version=profile.schema_version,
            evidence_verified=True,
        )
