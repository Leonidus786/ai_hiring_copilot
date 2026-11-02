"""Provider contracts and a deterministic offline fake implementation."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Protocol, runtime_checkable

from .schemas import CandidateProfile, ResumeSourcePage


@runtime_checkable
class ResumeExtractionProvider(Protocol):
    """Minimal provider-neutral interface for structured resume extraction."""

    provider_name: str
    model_name: str

    def extract(self, pages: Sequence[ResumeSourcePage]) -> Mapping[str, object] | CandidateProfile:
        """Return untrusted structured output; the service validates it."""
        ...


class FakeResumeExtractionProvider:
    """Deterministic, network-free provider for tests and local development.

    It intentionally understands only explicit ``Name:`` and ``Skills:`` lines.
    It is not an NLP parser and must never be presented as an AI extraction model.
    """

    provider_name = "fake"
    model_name = "deterministic-regex-v1"

    _SKILL_LINE = re.compile(r"^\s*skills\s*:\s*(.+?)\s*$", re.IGNORECASE)
    _NAME_LINE = re.compile(r"^\s*(?:candidate|name)\s*:\s*(.+?)\s*$", re.IGNORECASE)

    _CATEGORY_BY_SKILL = {
        "python": "programming_language",
        "sql": "database",
        "fastapi": "framework",
        "javascript": "programming_language",
        "typescript": "programming_language",
        "java": "programming_language",
        "pytorch": "framework",
        "tensorflow": "framework",
        "pandas": "library",
        "scikit-learn": "library",
    }

    def extract(self, pages: Sequence[ResumeSourcePage]) -> CandidateProfile:
        skills: list[dict[str, object]] = []
        full_name: dict[str, object] | None = None

        for page in pages:
            for raw_line in page.text.splitlines():
                line = raw_line.strip()
                if not line:
                    continue

                name_match = self._NAME_LINE.match(line)
                if name_match and full_name is None:
                    full_name = {
                        "value": name_match.group(1).strip(),
                        "evidence": {"page_number": page.page_number, "quote": line},
                    }
                    continue

                skill_match = self._SKILL_LINE.match(line)
                if not skill_match:
                    continue

                for raw_skill in skill_match.group(1).split(","):
                    skill_name = raw_skill.strip()
                    if not skill_name:
                        continue
                    skills.append(
                        {
                            "name": skill_name,
                            "category": self._CATEGORY_BY_SKILL.get(skill_name.casefold(), "other"),
                            "proficiency": None,
                            "evidence": [
                                {"page_number": page.page_number, "quote": line}
                            ],
                        }
                    )

        result: dict[str, object] = {"skills": skills}
        if full_name is not None:
            result["full_name"] = full_name
        return CandidateProfile.model_validate(result)
