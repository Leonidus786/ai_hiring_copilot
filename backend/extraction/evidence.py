"""Strict source-quote verification for extracted resume claims."""

from __future__ import annotations

import re
from collections.abc import Iterator

from .schemas import CandidateProfile, ResumeSourcePage, SourceEvidence


class EvidenceValidationError(Exception):
    """Raised when a claimed source quote cannot be found on its cited page."""

    def __init__(self, invalid_paths: list[str]) -> None:
        self.invalid_paths = tuple(invalid_paths)
        # Do not include source text, candidate PII, or the rejected quote in errors.
        super().__init__(f"Evidence verification failed for {len(invalid_paths)} claim(s).")


def _normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _iter_evidence(profile: CandidateProfile) -> Iterator[tuple[str, SourceEvidence]]:
    if profile.full_name and profile.full_name.evidence:
        yield "full_name", profile.full_name.evidence
    if profile.email and profile.email.evidence:
        yield "email", profile.email.evidence
    if profile.phone and profile.phone.evidence:
        yield "phone", profile.phone.evidence

    collections = (
        ("skills", profile.skills),
        ("work_experience", profile.work_experience),
        ("projects", profile.projects),
        ("education", profile.education),
        ("certifications", profile.certifications),
    )
    for collection_name, records in collections:
        for index, record in enumerate(records):
            for evidence_index, evidence in enumerate(record.evidence):
                yield f"{collection_name}[{index}].evidence[{evidence_index}]", evidence
            if collection_name == "skills":
                for evidence_index, evidence in enumerate(record.proficiency_evidence):
                    yield (
                        f"skills[{index}].proficiency_evidence[{evidence_index}]",
                        evidence,
                    )


def verify_profile_evidence(
    profile: CandidateProfile,
    pages: list[ResumeSourcePage] | tuple[ResumeSourcePage, ...],
) -> None:
    """Require every cited quote to be an exact whitespace-normalized page substring.

    This proves quote presence only. It does not prove that a quote logically
    supports every field in a record; semantic support still needs evaluation
    and human review.
    """

    page_text = {page.page_number: _normalize_whitespace(page.text) for page in pages}
    invalid_paths: list[str] = []

    for path, evidence in _iter_evidence(profile):
        source = page_text.get(evidence.page_number)
        if source is None or _normalize_whitespace(evidence.quote) not in source:
            invalid_paths.append(path)

    if invalid_paths:
        raise EvidenceValidationError(invalid_paths)
