"""
OpenArt — where the artist studied: "have studied at a Flemish or Brussels Conservatoire", "graduated
from Villa Arson", "or study at an educational institution in Norway", against the schools in the
artist's profile (ArtistProfile.education, pre-filled from the CV's Education section).

A study requirement names one of three things (a value can hold several; the most specific one used):
  institutions   "Villa Arson", "KU Leuven"        the school's name contains it
  study_places   "Ghent", "Flanders", "Hesse"      the school's city or name is there (a region
                                                   counts its main cities, REGION_CITIES)
  study_countries ["BE"]                           the school is in one of these countries

Like languages and career stage, it can PASS (one of the artist's schools matches) or stay a CHECK.
It never FAILS: a CV can leave a school out, and "the profile doesn't list it" is not "never studied
there".

    parse_study("have studied or are studying at a Flemish or Brussels Conservatoire.")
    -> {"study_places": ["Brussels", "Flanders"], "study_countries": ["BE"]}
"""

import re

from pydantic import BaseModel

from src.eligibility.geo import COUNTRY_RE, NAME_TO_COUNTRY, describe_countries


class EducationEntry(BaseModel):
    """One school in the artist's profile."""
    institution: str
    city: str | None = None
    country: str | None = None   # ISO 3166-1 alpha-2


# regions that calls name, with the cities their art schools are in (a school in Ghent is in Flanders).
# Short on purpose: a city that is missing only means a CHECK instead of a PASS.
REGION_CITIES = {
    "Flanders": ["Antwerp", "Antwerpen", "Ghent", "Gent", "Bruges", "Brugge", "Leuven", "Mechelen", "Hasselt",
                 "Genk", "Kortrijk"],
    "Brussels": ["Brussels", "Bruxelles", "Brussel"],
    "Wallonia": ["Liège", "Liege", "Mons", "Namur", "Charleroi", "Tournai"],
    "North Rhine-Westphalia": ["Cologne", "Köln", "Düsseldorf", "Dusseldorf", "Essen", "Dortmund", "Münster",
                               "Bonn", "Bochum", "Wuppertal"],
    "Hesse": ["Frankfurt", "Kassel", "Darmstadt", "Offenbach", "Wiesbaden", "Marburg", "Gießen", "Giessen"],
    "PACA": ["Nice", "Marseille", "Aix-en-Provence", "Toulon", "Avignon"],
}
REGION_COUNTRY = {"Flanders": "BE", "Brussels": "BE", "Wallonia": "BE", "North Rhine-Westphalia": "DE",
                  "Hesse": "DE", "PACA": "FR"}
# adjectives calls use for a region ("a Flemish conservatoire")
REGION_WORDS = {"flemish": "Flanders", "flanders": "Flanders", "brussels": "Brussels", "walloon": "Wallonia",
                "wallonia": "Wallonia", "north rhine-westphalia": "North Rhine-Westphalia", "nrw": "North Rhine-Westphalia",
                "hesse": "Hesse", "hessen": "Hesse", "hessian": "Hesse"}
REGION_WORD_RE = re.compile(r"\b(" + "|".join(sorted(map(re.escape, REGION_WORDS), key=len, reverse=True)) + r")\b",
                            re.IGNORECASE)

# "graduated from Villa Arson", "alumni of Villa Arson", "a graduate of Villa Arson": a named school
NAMED_SCHOOL_RE = re.compile(r"\b(?:graduated from|graduates? of|alumni of|studying at|study at|studied at)\s+"
                             r"(?:the\s+)?(?P<name>(?:[A-Z][\w'’-]+\s?){1,4})")
# "studied ... at/in a <place> conservatoire / academy / institution": a place of study
STUDY_RE = re.compile(r"\b(stud(y|ied|ies|ying)|graduat\w*|alumni|enrolled|education|training)\b", re.IGNORECASE)
STUDY_AT_RE = re.compile(r"\b(stud(y|ied|ying)|graduated)\b.{0,40}?\b(at|in|from)\b", re.IGNORECASE)
GENERIC_SCHOOL_WORDS = {"A", "An", "The", "Art", "Arts", "Educational", "School", "Academy", "University"}


def parse_study(text: str) -> dict | None:
    """The place or school a sentence asks the applicant to have studied at; None if it names none."""
    if not STUDY_RE.search(text):
        return None
    value: dict = {}
    if found := NAMED_SCHOOL_RE.search(text):
        name = found.group("name").strip()
        # a country or region after "studied at" is a place, not a school ("studied at a Flemish ...")
        if name.split()[0] not in GENERIC_SCHOOL_WORDS and not REGION_WORD_RE.fullmatch(name) \
                and not COUNTRY_RE.fullmatch(name):
            value["institutions"] = [name]
    # a place only with a study verb pointing at it ("studied ... at a Flemish conservatoire", "study in
    # Norway"): "Austrian citizens ... institutions" or "a university degree (NRW strand)" name no place of study
    if STUDY_AT_RE.search(text):
        places = sorted({REGION_WORDS[m.group(0).lower()] for m in REGION_WORD_RE.finditer(text)})
        countries = sorted({NAME_TO_COUNTRY[m.group(0).lower()] for m in COUNTRY_RE.finditer(text)}
                           | {REGION_COUNTRY[place] for place in places})
        if places:
            value["study_places"] = places
        if countries:
            value["study_countries"] = countries
    return value or None


def _school_matches(entry: EducationEntry, value: dict) -> bool:
    """Does one school meet the value? The most specific key decides: school name, then place, then country."""
    where = " ".join(filter(None, [entry.institution, entry.city])).lower()
    if names := value.get("institutions"):
        return any(name.lower() in where for name in names)
    if places := value.get("study_places"):
        towns = [town for place in places for town in [place] + REGION_CITIES.get(place, [])]
        return any(re.search(r"\b" + re.escape(town.lower()) + r"\b", where) for town in towns)
    if countries := value.get("study_countries"):
        return entry.country in countries
    return False


def study_check(value: dict, education: list[EducationEntry]) -> tuple[bool, str]:
    """(clearly met, the reason shown). Not met is a CHECK for the caller, never a FAIL."""
    wanted = (" or ".join(value.get("institutions") or value.get("study_places") or [])
              or describe_countries(value.get("study_countries", [])))
    if not education:
        return False, f"asks where you studied ({wanted}); your schools are not in your profile"
    for entry in education:
        if _school_matches(entry, value):
            return True, f"asks where you studied ({wanted}); you studied at {entry.institution}"
    return False, f"asks where you studied ({wanted}); not among the schools in your profile, check it"
