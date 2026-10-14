"""
OpenArt — what an application to one call needs (workflow.MD, "Step 6 — Application agent", sub-step 2).

Plain rules, no model call: the call's own extracted fields already say what to prepare.

- To draft: every application question, and every required material with kind "write"
  (statement, proposal, motivation letter...): the agent can draft these.
- To gather: every material with kind "gather" (CV, portfolio, budget, letters...), and any
  material not classified yet (kind None): safer to ask the artist for it than to draft it.

Each item may name the uploaded document that covers it ("cv", "statement", "portfolio"), found by
keyword on the item's name. The rules are deliberately narrow: a wrong ✓ would tell the artist they
have something they don't, while a missed match only leaves an item to tick by hand. A "write"
statement item can name the uploaded statement too: the artist can adapt it rather than start blank.

Whether that document is actually uploaded, and the artist's drafts and ticks, are added by the API
(api/applications.py): this module only reads the call, so it is the same for every artist.
"""

import hashlib
import re
from dataclasses import dataclass
from typing import Literal

from src.models.processed_opportunity import ProcessedOpportunity

# item name -> the uploaded document that covers it. Order matters: the first match wins.
DOCUMENT_RULES: list[tuple[str, re.Pattern]] = [
    ("cv", re.compile(r"\bcv\b|curriculum|r[eé]sum[eé]|\bbiograph|\bbio\b", re.I)),
    ("portfolio", re.compile(r"portfolio|dossier|work samples?|(samples?|examples?) of (your |recent |previous )?work",
                             re.I)),
    # an artist statement, not a "statement of intent" or a "statement on your plans" (those are
    # about this call's project, not the artist's practice)
    ("statement", re.compile(r"\b(artist'?s?|artistic) statement\b|statement (about|on|describing|of) "
                             r"(your |the )?(artistic )?(practice|work)\b", re.I)),
]


@dataclass
class ChecklistItem:
    key: str                            # stable id within the call: "q-<hash>" or "m-<hash>"
    kind: Literal["write", "gather"]
    source: Literal["question", "material"]
    title: str                          # the question, or the material's name ("CV")
    limit: str | None                   # the question's limit ("max 300 words") or the material's details
    document: str | None                # "cv" / "statement" / "portfolio" that covers it, or None


def item_key(prefix: str, text: str) -> str:
    """A short id from the item's text: stays the same as long as the call's text does, so a saved
    draft finds its item again after the corpus is re-exported (positions can shift, texts rarely do)."""
    return f"{prefix}-{hashlib.sha256(text.strip().lower().encode()).hexdigest()[:10]}"


# someone else's document ("Director's CV", "biography of the curator"): the artist's upload doesn't cover it
OTHER_PERSON = re.compile(r"director|producer|screenwriter|curator|restorer|conservator|partner|participant|"
                          r"member|mentor|collaborator|translator|author", re.I)


def matching_document(name: str) -> str | None:
    if OTHER_PERSON.search(name):
        return None
    for document, pattern in DOCUMENT_RULES:
        if pattern.search(name):
            return document
    return None


def build_checklist(call: ProcessedOpportunity) -> list[ChecklistItem]:
    """Every item the call asks for: questions first, then materials, each in the call's order.
    The English copy is used when there is one (as on the opportunity page)."""
    items: list[ChecklistItem] = []
    for q in call.application_questions_en or call.application_questions:
        items.append(ChecklistItem(key=item_key("q", q.question), kind="write", source="question",
                                   title=q.question, limit=q.limit, document=None))
    for m in call.required_materials_en or call.required_materials:
        document = matching_document(m.item)
        if m.kind == "write" and document != "statement":
            document = None   # only a statement can stand in for a text to write (adapted)
        items.append(ChecklistItem(key=item_key("m", m.item), kind="write" if m.kind == "write" else "gather",
                                   source="material", title=m.item, limit=m.details, document=document))
    # the same text twice (a call listing "CV" twice) would give two items with one key: keep the first
    unique: dict[str, ChecklistItem] = {}
    for i in items:
        unique.setdefault(i.key, i)
    return list(unique.values())
