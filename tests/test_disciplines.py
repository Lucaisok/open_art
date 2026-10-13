"""Tests for src/eligibility/disciplines.py. Run with: uv run pytest"""

import pytest

from src.eligibility.disciplines import discipline_match


@pytest.mark.parametrize("text, disciplines, expected", [
    ("Open to visual artists and photographers", ["Photography"], ("Photography", "photographers")),
    ("for painters, sculptors and printmakers", ["Visual Arts"], ("Visual Arts", "painters")),
    ("Grants for professional choreographers", ["Dance"], ("Dance", "choreographers")),
    # umbrella terms
    ("The residency is for artists working in the performing arts.", ["Dance"], ("Dance", "performing arts")),
    ("Open to visual arts practitioners", ["Photography"], ("Photography", "visual arts")),
    ("Artists of all disciplines are welcome to apply.", ["Music"], ("Music", "all disciplines")),
    # "all disciplines" narrowed by a named field
    ("Projects of all disciplines and genres of the independent performing arts", ["Design/Architecture"], None),
    ("Projects of all disciplines and genres of the independent performing arts", ["Dance"],
     ("Dance", "performing arts")),
    # no match
    ("The call is open to writers and poets.", ["Visual Arts"], None),
    ("Open to performing artists", ["Music"], None),                   # music is not under the umbrella
    ("", ["Dance"], None),
    ("Open to visual artists", [], None),                               # nothing in the profile
    ("Open to visual artists", ["Other/Non-Arts"], None),               # a discipline with no terms
    # a narrowing role: not the people who make the art
    ("Support for literary translators", ["Literature/Writing"], None),
    ("Organisers of music festivals may apply.", ["Music"], None),
    ("for dance teachers in secondary schools", ["Dance"], None),
    # not narrowing: "school age" is no role, and a role inside a list of examples illustrates a wider group
    ("Visual artists with children who are not yet of compulsory school age.", ["Visual Arts"],
     ("Visual Arts", "Visual artists")),
    ("Funding is available for professional artists and cultural practitioners (such as curators, producers or "
     "researchers) in all forms of art and culture.", ["Visual Arts"], ("Visual Arts", "all forms of art")),
    ("Open to cultural workers such as translators and publishers.", ["Literature/Writing"], None),
])
def test_discipline_match(text, disciplines, expected):
    assert discipline_match(text, disciplines) == expected


def test_word_boundaries():
    # "design" must not match inside "designated", "drama" inside "dramatically"
    assert discipline_match("in the designated area", ["Design/Architecture"]) is None
    assert discipline_match("the prices rose dramatically", ["Theatre"]) is None
