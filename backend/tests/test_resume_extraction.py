from __future__ import annotations

from collections.abc import Sequence

import pytest
from pydantic import ValidationError

from extraction.evidence import EvidenceValidationError, verify_profile_evidence
from extraction.providers import FakeResumeExtractionProvider
from extraction.schemas import CandidateProfile, ResumeSourcePage
from extraction.service import (
    ExtractionInputError,
    ExtractionProviderError,
    ResumeExtractionService,
    ResumeProfileValidationError,
)


SAMPLE_PAGE = ResumeSourcePage(
    page_number=1,
    text=(
        "Candidate: Sam Example\n"
        "Skills: Python, SQL, FastAPI\n"
        "Experience: Built internal data pipelines using Python.\n"
    ),
)


def test_fake_provider_extracts_skills_with_verbatim_evidence() -> None:
    result = ResumeExtractionService(FakeResumeExtractionProvider()).extract([SAMPLE_PAGE])

    assert result.provider_name == "fake"
    assert result.evidence_verified is True
    assert result.profile.full_name is not None
    assert result.profile.full_name.value == "Sam Example"
    assert [skill.name for skill in result.profile.skills] == ["Python", "SQL", "FastAPI"]
    assert result.profile.skills[0].evidence[0].quote == "Skills: Python, SQL, FastAPI"



def test_skill_proficiency_requires_separate_supporting_evidence() -> None:
    with pytest.raises(ValidationError):
        CandidateProfile.model_validate(
            {
                "skills": [
                    {
                        "name": "Python",
                        "proficiency": "advanced",
                        "evidence": [{"page_number": 1, "quote": "Skills: Python, SQL, FastAPI"}],
                    }
                ]
            }
        )


def test_skill_proficiency_evidence_is_verified() -> None:
    profile = CandidateProfile.model_validate(
        {
            "skills": [
                {
                    "name": "Python",
                    "proficiency": "advanced",
                    "evidence": [{"page_number": 1, "quote": "Skills: Python, SQL, FastAPI"}],
                    "proficiency_evidence": [
                        {"page_number": 1, "quote": "Built internal data pipelines using Python"}
                    ],
                }
            ]
        }
    )
    verify_profile_evidence(profile, [SAMPLE_PAGE])


def test_empty_candidate_fields_are_allowed_when_not_found() -> None:
    page = ResumeSourcePage(page_number=1, text="A resume with no recognized labels.")
    result = ResumeExtractionService(FakeResumeExtractionProvider()).extract([page])

    assert result.profile.full_name is None
    assert result.profile.skills == []


def test_evidence_requires_exact_quote_after_whitespace_normalization() -> None:
    profile = CandidateProfile.model_validate(
        {
            "skills": [
                {
                    "name": "Python",
                    "category": "programming_language",
                    "evidence": [
                        {"page_number": 1, "quote": "Skills: Python, SQL, FastAPI"}
                    ],
                }
            ]
        }
    )
    verify_profile_evidence(profile, [SAMPLE_PAGE])


def test_evidence_rejects_quote_not_present_on_cited_page() -> None:
    profile = CandidateProfile.model_validate(
        {
            "skills": [
                {
                    "name": "Kubernetes",
                    "category": "tool",
                    "evidence": [{"page_number": 1, "quote": "Used Kubernetes in production"}],
                }
            ]
        }
    )

    with pytest.raises(EvidenceValidationError) as exc_info:
        verify_profile_evidence(profile, [SAMPLE_PAGE])

    assert exc_info.value.invalid_paths == ("skills[0].evidence[0]",)
    assert "Used Kubernetes" not in str(exc_info.value)


def test_evidence_rejects_unknown_page_number() -> None:
    profile = CandidateProfile.model_validate(
        {
            "skills": [
                {
                    "name": "Python",
                    "evidence": [{"page_number": 2, "quote": "Skills: Python, SQL, FastAPI"}],
                }
            ]
        }
    )
    with pytest.raises(EvidenceValidationError):
        verify_profile_evidence(profile, [SAMPLE_PAGE])


def test_populated_contact_value_requires_evidence() -> None:
    with pytest.raises(ValidationError):
        CandidateProfile.model_validate({"full_name": {"value": "Sam Example"}})


def test_unknown_value_cannot_carry_evidence() -> None:
    with pytest.raises(ValidationError):
        CandidateProfile.model_validate(
            {
                "full_name": {
                    "value": None,
                    "evidence": {"page_number": 1, "quote": "Candidate: Sam Example"},
                }
            }
        )


def test_duplicate_skill_names_are_rejected_case_insensitively() -> None:
    with pytest.raises(ValidationError):
        CandidateProfile.model_validate(
            {
                "skills": [
                    {"name": "Python", "evidence": [{"page_number": 1, "quote": "Python"}]},
                    {"name": "python", "evidence": [{"page_number": 1, "quote": "Python"}]},
                ]
            }
        )


def test_extra_provider_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        CandidateProfile.model_validate({"unexpected": "should not be accepted"})


def test_input_requires_at_least_one_page() -> None:
    with pytest.raises(ExtractionInputError):
        ResumeExtractionService(FakeResumeExtractionProvider()).extract([])


def test_input_rejects_duplicate_page_numbers() -> None:
    service = ResumeExtractionService(FakeResumeExtractionProvider())
    with pytest.raises(ExtractionInputError):
        service.extract([SAMPLE_PAGE, SAMPLE_PAGE])


def test_provider_exception_is_sanitized() -> None:
    class BrokenProvider:
        provider_name = "broken"
        model_name = "test"

        def extract(self, pages: Sequence[ResumeSourcePage]) -> CandidateProfile:
            raise RuntimeError("private candidate text must not leak")

    with pytest.raises(ExtractionProviderError) as exc_info:
        ResumeExtractionService(BrokenProvider()).extract([SAMPLE_PAGE])

    assert "private candidate text" not in str(exc_info.value)


def test_invalid_provider_schema_is_rejected() -> None:
    class InvalidProvider:
        provider_name = "invalid"
        model_name = "test"

        def extract(self, pages: Sequence[ResumeSourcePage]) -> dict[str, object]:
            return {"skills": [{"name": "Python", "evidence": []}]}

    with pytest.raises(ResumeProfileValidationError):
        ResumeExtractionService(InvalidProvider()).extract([SAMPLE_PAGE])


def test_fake_provider_is_deterministic() -> None:
    provider = FakeResumeExtractionProvider()
    first = provider.extract([SAMPLE_PAGE])
    second = provider.extract([SAMPLE_PAGE])

    assert first.model_dump() == second.model_dump()
