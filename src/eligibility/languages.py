"""
OpenArt — language requirements: "a professional-level command of French and/or English" against the
languages the artist can work in (ArtistProfile.languages, pre-filled from the CV's Languages section).

The profile holds one list: the languages the artist can work in, at a fluent or professional level.
Calls nearly always ask for that level, so a separate "basic" level would rarely change a verdict.

Like career stage, a language sentence can PASS (the artist works in one of the accepted languages,
or in all of them when the call says "and") or stay a CHECK with a specific reason. It never FAILS:
levels are worded too loosely ("medium-high", "good knowledge") to turn someone away on.

    parse_languages("Applicants must be proficient in French or English.") -> {"languages": ["en", "fr"], "all": False}
    parse_languages("Please note that all sessions will be held in English.") -> None   (not a skill asked of you)
"""

import re

# ISO 639-1 code -> the English names a call or a CV uses for it (first = the name shown)
LANGUAGES = {
    "ar": ["Arabic"], "bg": ["Bulgarian"], "ca": ["Catalan"], "cs": ["Czech"], "da": ["Danish"],
    "de": ["German"], "el": ["Greek"], "en": ["English"], "es": ["Spanish", "Castilian"], "et": ["Estonian"],
    "eu": ["Basque"], "fa": ["Persian", "Farsi"], "fi": ["Finnish"], "fr": ["French"], "ga": ["Irish"],
    "he": ["Hebrew"], "hi": ["Hindi"], "hr": ["Croatian"], "hu": ["Hungarian"], "is": ["Icelandic"],
    "it": ["Italian"], "ja": ["Japanese"], "ko": ["Korean"], "lt": ["Lithuanian"], "lv": ["Latvian"],
    "mt": ["Maltese"], "nl": ["Dutch", "Flemish"], "no": ["Norwegian"], "pl": ["Polish"],
    "pt": ["Portuguese"], "ro": ["Romanian"], "ru": ["Russian"], "se": ["Sami", "Sámi"], "sk": ["Slovak"],
    "sl": ["Slovenian", "Slovene"], "sq": ["Albanian"], "sr": ["Serbian"], "sv": ["Swedish"],
    "sw": ["Swahili"], "tr": ["Turkish"], "uk": ["Ukrainian"], "zh": ["Chinese", "Mandarin"],
    "cy": ["Welsh"], "fy": ["Frisian"],
}
NAME_TO_LANGUAGE = {name.lower(): code for code, names in LANGUAGES.items() for name in names}
LANGUAGE_RE = re.compile(r"\b(" + "|".join(sorted(map(re.escape, NAME_TO_LANGUAGE), key=len, reverse=True)) + r")\b",
                         re.IGNORECASE)

# a language SKILL asked of the applicant: "proficient in", "command of", "speak", "knowledge of" ...
SKILL_RE = re.compile(r"\b(proficien\w*|fluen\w*|command of|speak\w*|spoken|knowledge of|language skills|"
                      r"level of|mastery of|master (of )?|able to (communicate|work|read|write) in|"
                      r"working knowledge|mother tongue|native)\b", re.IGNORECASE)
# languages that are about the work or the call, not the applicant: "works written in French",
# "translations into English", "applications may be submitted in English or Dutch"
NOT_A_SKILL_RE = re.compile(r"\b(translat\w*|written in|published in|submit\w*|applications? (may|can|must) be|"
                            r"in the (original )?language|into (english|\w+ish|\w+an)|"
                            # "the French-speaking art community of Belgium": a place, not a skill
                            r"speaking (art |artistic |cultural )?(community|communities|region|part|world|countr\w+))\b",
                            re.IGNORECASE)
# a wish, not a requirement: "not essential ... but an advantage", "knowledge of French is welcome"
NOT_REQUIRED_RE = re.compile(r"\b(not (essential|required|necessary|mandatory|a requirement)|advantage|welcome\w*|"
                             r"preferr\w*|preferabl\w*|asset|a plus|desirable|appreciated|helpful|useful)\b",
                             re.IGNORECASE)
ALL_RE = re.compile(r"\b(both|as well as)\b|\band\b(?!\s*/\s*or)", re.IGNORECASE)
EITHER_RE = re.compile(r"\bor\b|/", re.IGNORECASE)


def parse_languages(text: str) -> dict | None:
    """{"languages": [codes], "all": True if every one is needed} for a sentence that asks the applicant
    for a language skill; None when the sentence names no language skill or the languages are about
    the work (translations, the language of submission)."""
    if not SKILL_RE.search(text) or NOT_A_SKILL_RE.search(text) or NOT_REQUIRED_RE.search(text):
        return None
    codes = sorted({NAME_TO_LANGUAGE[found.group(0).lower()] for found in LANGUAGE_RE.finditer(text)})
    if not codes:
        return None
    # "French and/or English", "French or English" -> any one; "French and English" -> all
    between = text[LANGUAGE_RE.search(text).start():]
    needs_all = len(codes) > 1 and not EITHER_RE.search(between) and bool(ALL_RE.search(between))
    return {"languages": codes, "all": needs_all}


def language_names(codes: list[str]) -> str:
    return ", ".join(LANGUAGES[code][0] if code in LANGUAGES else code for code in codes)


def languages_check(value: dict, languages: list[str]) -> tuple[bool, str]:
    """(clearly met, the reason shown). Not met is a CHECK for the caller, never a FAIL."""
    asked = value["languages"]
    joiner = " and " if value["all"] else " or "
    wanted = joiner.join(LANGUAGES[code][0] if code in LANGUAGES else code for code in asked)
    if not languages:
        return False, f"asks for {wanted}; the languages you work in are not in your profile"
    yours = language_names(languages)
    met = all(code in languages for code in asked) if value["all"] else any(code in languages for code in asked)
    detail = f"asks for {wanted}; you work in {yours}"
    return met, detail if met else detail + ", check whether your level is enough"
