"""
OpenArt — does a DISCIPLINE sentence name one of the artist's disciplines?

Used by the engine (step 6b) to let a DISCIPLINE sentence PASS, never FAIL.
"Open to visual artists" passes a painter; anything it can't match stays a
CHECK, exactly as before. A wrong match can only produce a wrong "nothing
rules you out" (the artist reads the call and doesn't apply), never a wrong
rejection, so the table can afford to be simple.

Two guards keep a match from passing someone the sentence doesn't mean:
- a role word that narrows the discipline to something other than making the
  art: "literary TRANSLATORS", "music FESTIVALS", "dance TEACHERS" -> no match;
- only REQUIRES sentences are matched (the engine checks the polarity), so
  "Photography is not eligible" never passes a photographer.

    discipline_match("Open to visual artists and photographers", ["Photography"])
    -> ("Photography", "photographers")
"""

import re

# canonical discipline (CANONICAL_DISCIPLINES) -> the words that name it
TERMS = {
    "Visual Arts": [r"visual arts?", r"visual artists?", r"fine arts?", r"paint(ing|ings|ers?)", r"sculpt\w*",
                    r"drawings?", r"printmak\w*", r"graphic arts?"],
    "Performing Arts": [r"performing arts?", r"performance arts?", r"performers?"],
    "Music": [r"music\w*", r"composers?", r"sound arts?"],
    "Dance": [r"danc\w*", r"choreograph\w*"],
    "Theatre": [r"theat(re|er)s?", r"theatrical", r"drama", r"playwrights?", r"actors?", r"puppet\w*"],
    "Film/Video": [r"films?", r"filmmak\w*", r"cinema\w*", r"video", r"moving images?", r"animation"],
    "Literature/Writing": [r"literature", r"literary", r"writers?", r"authors?", r"poetry", r"poets?", r"fiction"],
    "Design/Architecture": [r"design(ers?)?", r"architect\w*"],
    "Digital/New Media Arts": [r"digital arts?", r"new media", r"media arts?"],
    "Craft": [r"crafts?", r"craftspe\w*", r"ceramic\w*", r"textile\w*", r"applied arts?"],
    "Photography": [r"photograph\w*"],
    "Curating/Art Criticism": [r"curat\w*", r"art critic\w*"],
    "Cultural Heritage": [r"cultural heritage"],
    "Circus/Street Arts": [r"circus\w*", r"street arts?"],
    "Multidisciplinary": [r"multidisciplinary", r"interdisciplinary", r"transdisciplinary"],
}

# umbrella terms: "performing arts" also names dance, theatre and circus; "visual arts" names photography
UMBRELLAS = {
    "Performing Arts": ["Dance", "Theatre", "Circus/Street Arts"],
    "Visual Arts": ["Photography"],
}

# open to every discipline: passes anyone with a discipline in their profile
ANY_DISCIPLINE_RE = re.compile(r"\b(all|any) (artistic |art )?(disciplines?|art forms?|fields of art)\b", re.IGNORECASE)

# a role or venue that narrows the discipline to something other than making the art
NARROWING_RE = re.compile(r"\b(translat\w*|teach\w*|educat\w*|festivals?|publish\w*|producers?|venues?|"
                          r"organi[sz]ers?|museums?|schools?|librar\w*)\b", re.IGNORECASE)

_TERM_RES = {canonical: re.compile(r"\b(" + "|".join(terms) + r")\b", re.IGNORECASE)
             for canonical, terms in TERMS.items()}


def discipline_match(text: str, disciplines: list[str]) -> tuple[str, str] | None:
    """(the artist's discipline that matched, the words that named it), or None."""
    if not disciplines or NARROWING_RE.search(text):
        return None
    # "all disciplines" only counts if the sentence names no specific one: "all disciplines and genres of
    # the independent performing arts" is open to performing arts only, not to everyone
    names_specific = any(term_re.search(text) for term_re in _TERM_RES.values())
    if not names_specific and (found := ANY_DISCIPLINE_RE.search(text)):
        return disciplines[0], found.group(0)
    for discipline in disciplines:
        # the artist's own discipline, or an umbrella that covers it
        named_by = [discipline] + [umbrella for umbrella, members in UMBRELLAS.items() if discipline in members]
        for canonical in named_by:
            # "Other/Non-Arts" has no terms: it never matches
            if canonical in _TERM_RES and (found := _TERM_RES[canonical].search(text)):
                return discipline, found.group(0)
    return None
