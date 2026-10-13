"""Tests for src/matching/explain.py: why a call is in an artist's results. Run with: uv run pytest"""

from tests.test_matcher import opp
from src.matching.explain import (ArtistText, Explainer, clean_sentences, common_words, explain,
                                  same_word)


def test_forms_of_a_word_match_but_unrelated_words_dont():
    assert same_word("sound", "soundscapes") and same_word("choreographer", "choreography")
    assert same_word("translate", "translation") and same_word("ecology", "ecological")
    assert not same_word("film", "films")           # under five letters: only the same word
    assert not same_word("painting", "pavilion") and not same_word("print", "prize")


def test_names_are_not_common_words():
    text = "I studied in Paris. Theatre is my work.\nPrintmaking and etching at Kunsthall Bergen."
    assert common_words(text) == {"studied", "theatre", "printmaking", "etching"}


def test_pdf_lines_become_sentences_and_list_entries_are_left_out():
    text = ("I record rivers and harbours with hydrophones and\ncontact microphones in many cities.\n"
            "2025 “Frames as Territories” (curator /\nSolo show")
    assert clean_sentences(text) == [
        "I record rivers and harbours with hydrophones and contact microphones in many cities."]


def calls():
    """Twenty calls: "residency" is in all of them, "sound" and "water" only in the first (5%)."""
    first = opp("water", title_en="Sound residency",
                description_en="A residency by the water for sound artists. Studios are open all year.")
    return [first] + [opp(f"c{i}", title_en=f"Painting residency {i}", description_en="Studios for painters.")
                      for i in range(19)]


def test_only_words_rare_in_the_corpus_explain_a_match():
    artist = ArtistText([("statement.md", "I make sound installations from recordings of water, "
                                          "and I am looking for a residency.")])
    e = explain(Explainer(calls()), artist, calls()[0])
    assert e.shared == ["Sound", "water"]           # "residency" is in every call: it explains nothing
    assert e.call_sentence == "A residency by the water for sound artists."
    assert e.call_highlight == ["water", "sound"]
    assert e.your_document == "statement.md" and e.your_highlight == ["sound", "water"]


def test_nothing_specific_in_common_is_a_broad_match():
    artist = ArtistText([("cv.pdf", "I make sound installations from recordings of water and rivers.")])
    e = explain(Explainer(calls()), artist, calls()[1])
    assert e.shared == [] and e.call_sentence is None and e.your_sentence is None
