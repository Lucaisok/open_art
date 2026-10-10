"""
OpenArt — the artist profile the eligibility engine matches against.

ArtistProfile v1 (decision 3, workflow.MD). Every field is optional: an empty
field never rejects anyone, it turns the requirement that needs it into a
CHECK item. Filled by a form for now; later pre-filled from the CV by the RAG
step and confirmed by the artist.

Countries are ISO 3166-1 alpha-2 codes ("BE", "NO"), the same codes the value
parsers produce (src/eligibility/geo.py).
"""

from datetime import date
from typing import Literal

from pydantic import BaseModel, field_validator

from src.eligibility.geo import COUNTRIES
from src.eligibility.languages import LANGUAGES
from src.eligibility.study import EducationEntry
from src.processing.canonicalize import CANONICAL_CAREER_STAGES, CANONICAL_DISCIPLINES

ApplicantType = Literal["individual", "group", "organisation"]


def _country_code(code: str) -> str:
    code = code.strip().upper()
    if code not in COUNTRIES:
        raise ValueError(f"unknown country code {code!r} (expected ISO 3166-1 alpha-2, e.g. 'BE')")
    return code


class ArtistProfile(BaseModel):
    birth_date: date | None = None
    nationalities: list[str] = []           # every citizenship the artist holds; [] = not given
    residence_country: str | None = None    # where the artist lives now
    applicant_type: ApplicantType | None = None  # who applies: a person, a group/collective, an organisation
    disciplines: list[str] = []             # CANONICAL_DISCIPLINES
    career_stage: str | None = None         # CANONICAL_CAREER_STAGES
    years_active: int | None = None
    currently_enrolled: bool | None = None  # enrolled in any study programme right now
    graduation_year: int | None = None      # year of the most recent graduation
    has_degree: bool | None = None
    degree_field: str | None = None
    education: list[EducationEntry] = []    # the schools the artist studied at; [] = not given
    languages: list[str] = []               # ISO 639-1 codes of the languages the artist can work in
                                            # (fluent / professional level); [] = not given

    @field_validator("education")
    @classmethod
    def _check_education(cls, entries: list[EducationEntry]) -> list[EducationEntry]:
        for entry in entries:
            entry.institution = entry.institution.strip()
            if not entry.institution:
                raise ValueError("every school needs a name")
            entry.city = (entry.city or "").strip() or None
            entry.country = None if not entry.country else _country_code(entry.country)
        return entries

    @field_validator("languages")
    @classmethod
    def _check_languages(cls, codes: list[str]) -> list[str]:
        codes = sorted({code.strip().lower() for code in codes})
        if unknown := [code for code in codes if code not in LANGUAGES]:
            raise ValueError(f"unknown language code(s) {unknown} (expected ISO 639-1, e.g. 'en')")
        return codes

    @field_validator("nationalities")
    @classmethod
    def _check_nationalities(cls, codes: list[str]) -> list[str]:
        return sorted({_country_code(code) for code in codes})

    @field_validator("residence_country")
    @classmethod
    def _check_residence(cls, code: str | None) -> str | None:
        return None if code is None else _country_code(code)

    @field_validator("disciplines")
    @classmethod
    def _check_disciplines(cls, values: list[str]) -> list[str]:
        unknown = [v for v in values if v not in CANONICAL_DISCIPLINES]
        if unknown:
            raise ValueError(f"unknown discipline(s) {unknown}; expected one of {CANONICAL_DISCIPLINES}")
        return values

    @field_validator("career_stage")
    @classmethod
    def _check_career_stage(cls, value: str | None) -> str | None:
        if value is not None and value not in CANONICAL_CAREER_STAGES:
            raise ValueError(f"unknown career stage {value!r}; expected one of {CANONICAL_CAREER_STAGES}")
        return value
