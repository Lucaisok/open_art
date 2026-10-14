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

An item to gather that asks for pictures of the artist's work ("Images of previous works", "visual
documentation material", "JPG or PNG preview") is marked `images`: the artist can choose images of
their saved projects for it (api/applications.py). Not a photo of the person (ID, profile, headshot).

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
    images: bool = False                # asks for pictures of the work: chosen from the projects' images


def item_key(prefix: str, text: str) -> str:
    """A short id from the item's text: stays the same as long as the call's text does, so a saved
    draft finds its item again after the corpus is re-exported (positions can shift, texts rarely do)."""
    return f"{prefix}-{hashlib.sha256(text.strip().lower().encode()).hexdigest()[:10]}"


# someone else's document ("Director's CV", "biography of the curator"): the artist's upload doesn't cover it
OTHER_PERSON = re.compile(r"director|producer|screenwriter|curator|restorer|conservator|partner|participant|"
                          r"member|mentor|collaborator|translator|author", re.I)


# pictures of the work (checked on the item's name only, on items to gather)
IMAGES = re.compile(r"\b(images?|photos?|photographs?|pictures?|jpe?gs?|png|stills?|visual (material|documentation)|"
                    r"documentation of (your |the |previous |recent |completed )?(works?|products?|projects?))\b", re.I)
# pictures of the person, not the work
NOT_THE_WORK = re.compile(r"\b(identity|id|passport|profile|headshot|portrait|group photos?|selfie)\b", re.I)


def asks_for_images(name: str) -> bool:
    return bool(IMAGES.search(name)) and not NOT_THE_WORK.search(name)


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
        kind = "write" if m.kind == "write" else "gather"
        items.append(ChecklistItem(key=item_key("m", m.item), kind=kind, source="material", title=m.item,
                                   limit=m.details, document=document,
                                   images=kind == "gather" and asks_for_images(m.item)))
    # the same text twice (a call listing "CV" twice) would give two items with one key: keep the first
    unique: dict[str, ChecklistItem] = {}
    for i in items:
        unique.setdefault(i.key, i)
    return list(unique.values())
