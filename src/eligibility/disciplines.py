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
                    r"drawings?", r"printmak\w*", r"graphic arts?", r"contemporary arts?", r"visual cultures?",
                    r"plastic arts?", r"illustrat(ion|ions|ors?)", r"installations?", r"print techniques?"],
    "Performing Arts": [r"performing arts?", r"performance arts?", r"performers?", r"performance",
                        r"performance artists?", r"live arts?"],
    "Music": [r"music\w*", r"composers?", r"sound arts?", r"sound artists?", r"bands?", r"singers?", r"vocal\w*",
              r"instrumental\w*", r"songwrit\w*", r"orchestra\w*", r"opera", r"pop-rock", r"jazz", r"concerts?"],
    "Dance": [r"danc\w*", r"choreograph\w*"],
    "Theatre": [r"theat(re|er)s?", r"theatrical", r"drama", r"playwrights?", r"actors?", r"puppet\w*",
                r"stage works?"],
    "Film/Video": [r"films?", r"filmmak\w*", r"cinema\w*", r"video\w*", r"moving[- ]images?", r"animation",
                   r"audiovisual", r"documentar(y|ies)", r"short films?", r"film-makers?"],
    "Literature/Writing": [r"literature", r"literary", r"writers?", r"authors?", r"poetry", r"poets?", r"fiction",
                           r"writing", r"novels?", r"essay\w*", r"comics?", r"storytell\w*", r"prose"],
    "Design/Architecture": [r"design(ers?)?", r"architect\w*", r"urbanism"],
    "Digital/New Media Arts": [r"digital arts?", r"new media", r"media arts?", r"digital media", r"multimedia",
                               r"digital and computational", r"computational", r"data visuali[sz]ation"],
    "Craft": [r"crafts?", r"craftspe\w*", r"ceramic\w*", r"textile\w*", r"applied arts?", r"artisans?"],
    "Photography": [r"photograph\w*"],
    "Curating/Art Criticism": [r"curat\w*", r"art critic\w*", r"critics?", r"art observers?", r"theorists?",
                               r"art writ(ers?|ing)"],
    "Cultural Heritage": [r"cultural heritage"],
    "Circus/Street Arts": [r"circus\w*", r"street arts?"],
    "Multidisciplinary": [r"multidisciplinary", r"interdisciplinary", r"transdisciplinary", r"trans\W*disciplinary",
                          r"cross-?disciplinary", r"multi-?art", r"across disciplines"],
}

# umbrella terms: "performing arts" also names dance, theatre and circus; "visual arts" names photography
UMBRELLAS = {
    "Performing Arts": ["Dance", "Theatre", "Circus/Street Arts"],
    "Visual Arts": ["Photography"],
}

# open to every discipline: passes anyone with a discipline in their profile
ANY_DISCIPLINE_RE = re.compile(r"\b((all|any|every) (artistic |art |creative )?(disciplines?|art forms?|fields of art|"
                               r"artistic fields?|forms of (art|artistic expression))|regardless of (their )?discipline)\b",
                               re.IGNORECASE)

# any artistic practice, no discipline named ("a recognised professional artistic practice", "one or more of the
# artistic areas"): mined from the discipline sentences the term table didn't read (step 4)
GENERIC_PRACTICE_RE = re.compile(r"\b(recogni[sz]ed|professional) (artistic|creative) practice\b"
                                 r"|\bone or more of the artistic areas\b|\bartists of all\b"
                                 r"|\b(cultural and artistic|artistic and cultural) (field|sector)s?\b", re.IGNORECASE)

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
    if not names_specific and (found := ANY_DISCIPLINE_RE.search(text) or GENERIC_PRACTICE_RE.search(text)):
        return disciplines[0], found.group(0)
    for discipline in disciplines:
        # the artist's own discipline, or an umbrella that covers it
        named_by = [discipline] + [umbrella for umbrella, members in UMBRELLAS.items() if discipline in members]
        for canonical in named_by:
            # "Other/Non-Arts" has no terms: it never matches
            if canonical in _TERM_RES and (found := _TERM_RES[canonical].search(text)):
                return discipline, found.group(0)
    return None


def disciplines_named(text: str) -> list[tuple[str, str]]:
    """Every discipline the sentence names: (canonical discipline, the words that named it).
    Used to explain a discipline sentence that doesn't match the artist (the engine's CHECK reason)."""
    return [(canonical, found.group(0)) for canonical, term_re in _TERM_RES.items()
            if (found := term_re.search(text))]


def narrowing_word(text: str) -> str | None:
    """The role or venue word that narrows the sentence ("translators", "festivals"), if any."""
    found = NARROWING_RE.search(text)
    return found.group(0) if found else None
