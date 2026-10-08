"""Tests for src/rag/profile_prefill.py. No API calls: a fake OpenAI client returns a canned answer,
and the passages are made by hand (or retrieved with a fake embedder). Run with: uv run pytest"""

import os
from datetime import date
from types import SimpleNamespace

from src.eligibility.profile import ArtistProfile
from src.rag.knowledge_base import ArtistKnowledgeBase, KnowledgeChunk, RetrievedPassage
from src.rag.profile_prefill import (
    LLMAnswer,
    build_profile,
    check_answer,
    gather_passages,
    prefill_profile,
    quote_is_in,
)
from tests.test_rag_retrieval import ILKA, KeywordEmbedder

TODAY = date(2026, 10, 8)


def passage(text, section, document="cv.pdf", index=0, page=1):
    chunk = KnowledgeChunk(chunk_id=f"{document}#{index}", document=document, index=index, section=section,
                           text=text, page=page)
    return RetrievedPassage(chunk=chunk, score=0.5)


PASSAGES = [
    passage("Born 12 March 1994 in Debrecen, Hungary\nCitizenship: Hungarian\nLives and works in Vienna, Austria",
            "PERSONAL DETAILS"),
    passage("2006–2010 BA in Music Technology, Universidade Federal\nNot currently enrolled in any study programme",
            "Education", document="cv.docx", index=2, page=None),
    passage("2021 Rain Score (performance), Casa da Música, Porto", "Exhibitions", document="cv.docx", index=3,
            page=None),
]


def answer(**fields):
    """An LLMAnswer with every field null except the ones given."""
    return LLMAnswer(**{name: None for name in LLMAnswer.model_fields} | fields)


class FakeClient:
    """Stands in for OpenAI(): records the messages it was sent and returns a fixed answer."""
    def __init__(self, parsed):
        self.sent = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(parse=self._parse))
        self._parsed = parsed

    def _parse(self, **kwargs):
        self.sent.append(kwargs["messages"])
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed=self._parsed))])


# -- quote check -----------------------------------------------------------------------------------------

def test_quote_check_ignores_case_line_breaks_and_dash_style_but_not_words():
    text = PASSAGES[1].chunk.text
    assert quote_is_in("2006-2010 BA in music technology", text)          # en dash copied as a hyphen
    assert quote_is_in("Universidade Federal Not currently enrolled", text)  # across a line break
    assert not quote_is_in("Currently enrolled in an MA programme", text)
    assert not quote_is_in("   ", text)                                     # an empty quote proves nothing


# -- checking the LLM's answer ---------------------------------------------------------------------------

def test_valid_answers_become_proposals_in_profile_format_with_citations():
    result = check_answer(answer(
        birth_date={"passage": "P1", "quote": "Born 12 March 1994", "value": "1994-03-12"},
        nationalities={"passage": "P1", "quote": "Citizenship: Hungarian", "value": ["hu"]},
        currently_enrolled={"passage": "P2", "quote": "Not currently enrolled in any study programme",
                            "value": False},
        active_since={"passage": "P3", "quote": "2021 Rain Score", "value": 2021},
    ), PASSAGES, today=TODAY)
    values = {p.field: p.value for p in result.proposals}
    assert values == {"birth_date": date(1994, 3, 12), "nationalities": ["HU"], "currently_enrolled": False,
                      "years_active": 5}
    assert result.rejected == []
    years = next(p for p in result.proposals if p.field == "years_active")
    assert years.note == "active since 2021" and years.citation == "cv.docx · Exhibitions"
    assert next(p for p in result.proposals if p.field == "birth_date").citation == "cv.pdf · p. 1 · PERSONAL DETAILS"


def test_made_up_quotes_and_unknown_passages_are_dropped():
    result = check_answer(answer(
        residence_country={"passage": "P1", "quote": "Lives in Berlin, Germany", "value": "DE"},
        graduation_year={"passage": "P9", "quote": "2010", "value": 2010},
    ), PASSAGES, today=TODAY)
    assert result.proposals == []
    assert [name for name, _ in result.rejected] == ["residence_country", "graduation_year"]


def test_values_the_profile_would_refuse_are_dropped():
    result = check_answer(answer(
        nationalities={"passage": "P1", "quote": "Citizenship: Hungarian", "value": ["Hungary"]},
        birth_date={"passage": "P1", "quote": "Born 12 March 1994", "value": "12 March 1994"},
        active_since={"passage": "P3", "quote": "2021 Rain Score", "value": 2031},
    ), PASSAGES, today=TODAY)
    assert result.proposals == []
    assert {name for name, _ in result.rejected} == {"nationalities", "birth_date", "active_since"}


def test_fields_the_llm_leaves_null_are_not_proposed():
    assert check_answer(answer(), PASSAGES, today=TODAY).proposals == []


# -- the whole flow, and the confirm step ---------------------------------------------------------------

def test_only_retrieved_passages_are_sent_and_only_from_the_chosen_documents(tmp_path):
    kb = ArtistKnowledgeBase("ilka_varga", root=str(tmp_path), embedder=KeywordEmbedder())
    kb.add_document(os.path.join(ILKA, "cv.pdf"))
    kb.add_document(os.path.join(ILKA, "statement.docx"))

    passages = gather_passages(kb, documents=["cv.pdf"])
    assert {p.chunk.document for p in passages} == {"cv.pdf"}
    assert len({p.chunk.chunk_id for p in passages}) == len(passages)  # each passage once

    client = FakeClient(answer(has_degree={"passage": "P1", "quote": passages[0].chunk.text[:20], "value": True}))
    result = prefill_profile(kb, documents=["cv.pdf"], client=client, today=TODAY)
    sent = client.sent[0][1]["content"]
    assert all(p.chunk.text in sent for p in result.passages)
    assert "statement.docx" not in sent
    assert [p.field for p in result.proposals] == ["has_degree"]


def test_profile_holds_only_confirmed_proposals_on_top_of_what_the_artist_entered():
    proposals = check_answer(answer(
        birth_date={"passage": "P1", "quote": "Born 12 March 1994", "value": "1994-03-12"},
        nationalities={"passage": "P1", "quote": "Citizenship: Hungarian", "value": ["HU"]},
    ), PASSAGES, today=TODAY).proposals
    accepted = [p for p in proposals if p.field == "nationalities"]   # the artist declined the birth date
    profile = build_profile(accepted, base=ArtistProfile(residence_country="AT"))
    assert profile.nationalities == ["HU"] and profile.residence_country == "AT" and profile.birth_date is None
