# the core schema, this is what every other file ultimately produces.
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ApplicationQuestion(BaseModel):
    """One question or prompt the application form asks, copied verbatim (for the application agent)."""
    question: str
    limit: str | None = None  # stated length limit, verbatim ("max 300 words"); None if none stated


class RequiredMaterial(BaseModel):
    """One thing the applicant must submit (CV, portfolio, budget, letters...)."""
    item: str                 # short name, may be paraphrased ("Portfolio")
    details: str | None = None  # stated limits: pages, size, format
    quote: str                # the call's own sentence asking for it, verbatim - checked in code
    # for the application agent (workflow.MD, "Step 6"): "write" = text the applicant writes for this
    # call (statement, proposal, motivation letter...), the agent can draft it; "gather" = something
    # they already have or must obtain (CV, portfolio, budget, letters, ID...). None = not classified yet
    kind: Literal["write", "gather"] | None = None


class RawOpportunity(BaseModel):
    id: str

    source: str
    source_url: str
    application_url: str | None = None
    # linked PDFs (call text, guidelines) whose text the extraction read alongside the page,
    # so every requirement can be traced back to its document; [] = page text only
    document_urls: list[str] = []

    title: str
    organisation: str | None = None

    description: str | None = None
    discipline: str | None = None
    opportunity_type: str | None = None
    country: str | None = None
    city: str | None = None
    funding: str | None = None
    application_fee: str | None = None
    career_stage: str | None = None

    # Since the combined re-extraction (workflow.MD, "Step 3"): ONLY the conditions the artist must
    # meet to be allowed to apply - the classifier and eligibility engine read this field alone.
    # Records extracted before that hold the older, broader block (project rules, procedure too).
    requirements_text: str

    deadline: str | None = None  # verbatim, with time/timezone and every round when stated

    # -- added by the combined re-extraction; defaults keep older records loading unchanged --
    open_to: list[str] = []                   # who may apply: "individuals" / "groups" / "organisations"
    project_requirements: str | None = None   # what the project must meet (verbatim); shown, never checked
    how_to_apply: str | None = None           # procedure, materials, how to submit (verbatim)
    application_questions: list[ApplicationQuestion] = []
    required_materials: list[RequiredMaterial] = []
    selection_criteria: str | None = None     # what the jury judges on (verbatim)
    application_language: str | None = None   # language(s) applications must be written in
    submission_method: str | None = None      # "online form" | "email" | "portal" | "post" | "other"
    program_dates: str | None = None          # residency period / project timeline (verbatim)
    rolling_deadline: bool = False            # applications accepted continuously, no closing date
    rules_in_external_document: bool = False  # the call says its rules are in a document we didn't read
    # verbatim fields whose text was not found in the page text (see extraction.verbatim_misses):
    # a paraphrase to check, not to trust
    verbatim_flags: list[str] = []
    # the page text (+ linked PDF text) the model read, so a later prompt change can re-run
    # without re-crawling pages that may have closed meanwhile
    source_text: str | None = None

    collected_at: datetime
