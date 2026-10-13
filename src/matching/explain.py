"""
OpenArt — why a call is in an artist's results, in words they can check.

The ranking compares whole texts (one embedding per call, one per artist document), so it has no
"reason" of its own. Quoting the call's sentence closest to the artist was tried first and read
badly: the closest sentence is often generic open-call language ("a multidisciplinary research
programme"), and on the artist's side a PDF line ("2025 “Frames as Territories” (curator /").

So the explanation is the WORDS the call and the artist's documents share, counting only words
that are rare in the corpus (in fewer than SPECIFIC_MAX_SHARE of the calls): "sound", "etching",
"choreography" count; "artists", "programme", "visual" don't. Then:
  - shared words found: they are shown, with the call's sentence (and the artist's) that holds most
  - none: the call is a BROAD match (open to the artist's field, nothing specific in common),
    and the page says so instead of quoting a sentence that only looks related.

Plain string rules, no model: deterministic and easy to audit (workflow.MD "Why this call").

    explainer = Explainer(opportunities)                       # once, with the Matcher
    artist = ArtistText([("statement.pdf", text), ...])       # once per request
    explain(explainer, artist, opportunity)
    -> Explanation(shared=["sound", "water"], call_sentence="A residency for sound art ...",
                   call_highlight=["sound"], your_sentence="I record rivers ...", ...)
"""

import re
from dataclasses import dataclass, field

from src.eligibility.chunking import split_into_chunks
from src.models.processed_opportunity import ProcessedOpportunity

# a word in fewer than this share of the calls is specific enough to explain a match
SPECIFIC_MAX_SHARE = 0.10
MIN_WORD = 4                 # shorter words are too ambiguous to show ("art", "new")
MIN_PREFIX = 5               # "sound" ~ "soundscapes": two words match on a shared beginning this long...
PREFIX_SLACK = 2             # ...that covers all but this many letters of the shorter word

# words with no topic, kept out whatever their frequency (frequency alone lets rare filler through)
STOP_WORDS = set("""
about above after again also although among another apply applicant applicants application applications
around based because been before being below between both call calls cannot could during each either
every from further have having here into itself just more most must only other over same selected
should since some such than that their them then there these they this those though through under
until upon very were what when where which while whom whose will with within without would your yours
year years month months week weeks days work works working artist artists open project projects
programme program offer offers include includes including support supports page information
time times looking look small large long short connect connection centre center format formats
setting settings question questions follow followed following realize realise realised realized
european europe international national local place places people world life part parts level
opportunity opportunities possible interest interested interests focus focused aims explore
exploring practice practices process create creating creation make making based early career
emerging professional young together across today future field fields form forms kind kinds
foundation foundations
""".split())

WORD_RE = re.compile(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ'’-]*[A-Za-zÀ-ÿ]")
YEAR_START_RE = re.compile(r"^\s*[(\[]?\d{4}")
# a line break inside a sentence (PDF text): the next line starts in lower case, or the line before
# doesn't end a sentence
SOFT_BREAK_RE = re.compile(r"(?<![.!?:;])\n(?=\s*[a-zà-ÿ(“\"'])")
MIN_SENTENCE_WORDS = 8


def words(text: str) -> list[tuple[str, str]]:
    """The topic words of a text, in order: (as written, lower case). Stop words and short words out."""
    found = []
    for match in WORD_RE.finditer(text or ""):
        word = match.group().strip("'’-")
        lower = word.lower()
        if len(lower) >= MIN_WORD and lower not in STOP_WORDS:
            found.append((word, lower))
    return found


# a word right after the start of the text or of a sentence or line: capitalized because it comes first
SENTENCE_START_RE = re.compile(r"(?:^|[.!?:;\n•]\s*)$")


def common_words(text: str) -> set[str]:
    """The topic words a text uses as ordinary words: written in lower case at least once, or
    capitalized only because they start a sentence or line. Names ("Paris", "Ruído Comum") are left out."""
    found = set()
    for match in WORD_RE.finditer(text or ""):
        word = match.group().strip("'’-")
        lower = word.lower()
        if len(lower) < MIN_WORD or lower in STOP_WORDS:
            continue
        if word[0].islower() or SENTENCE_START_RE.search(text[max(0, match.start() - 3):match.start()]):
            found.add(lower)
    return found


def same_word(a: str, b: str) -> bool:
    """"sound" ~ "sounds" ~ "soundscapes", "translate" ~ "translation": equal, or a shared beginning
    of at least MIN_PREFIX letters covering all but PREFIX_SLACK letters of the shorter word."""
    if a == b:
        return True
    shorter = min(len(a), len(b))
    if shorter < MIN_PREFIX:
        return False
    common = 0
    while common < shorter and a[common] == b[common]:
        common += 1
    return common >= max(MIN_PREFIX, shorter - PREFIX_SLACK)


def clean_sentences(text: str) -> list[str]:
    """The artist's text as whole sentences: PDF line breaks inside a sentence joined, and list
    entries ("2025 Frames as Territories (curator /"), short fragments and number-heavy lines left out."""
    text = SOFT_BREAK_RE.sub(" ", text or "")
    sentences = []
    for sentence in split_into_chunks(text):
        sentence = re.sub(r"\s+", " ", sentence).strip()
        if len(sentence.split()) < MIN_SENTENCE_WORDS or YEAR_START_RE.match(sentence):
            continue
        if sum(c.isalpha() for c in sentence) / len(sentence) < 0.7:
            continue
        sentences.append(sentence)
    return sentences


def call_text(opp: ProcessedOpportunity) -> str:
    """What the explanation reads of a call: what it is about (the same fields as its embedding)."""
    return f"{opp.title_en}\n{opp.description_en or ''}"


class Explainer:
    """Knows how common each word is across the corpus, built once with the Matcher (~0.1 s)."""

    def __init__(self, opportunities: list[ProcessedOpportunity]):
        counts: dict[str, int] = {}
        for opp in opportunities:
            for lower in {lower for _, lower in words(call_text(opp))}:
                counts[lower] = counts.get(lower, 0) + 1
        self._calls = max(len(opportunities), 1)
        # grouped by their first MIN_PREFIX letters: only words in the same group can be the same word
        self._groups: dict[str, list[tuple[str, int]]] = {}
        for word, n in counts.items():
            self._groups.setdefault(word[:MIN_PREFIX], []).append((word, n))
        self._specific: dict[str, bool] = {}   # answers so far

    def is_specific(self, lower: str) -> bool:
        """Rare in the corpus, counting its forms ("sound" and "sounds" together). An approximation:
        a call using two forms counts twice, which only makes a word look a little more common."""
        if lower not in self._specific:
            calls = sum(n for word, n in self._groups.get(lower[:MIN_PREFIX], []) if same_word(word, lower))
            self._specific[lower] = calls / self._calls < SPECIFIC_MAX_SHARE
        return self._specific[lower]

    def shared_words(self, artist: set[str], text: str) -> list[str]:
        """The specific words of `text` (a call's) that the artist also uses (`artist`: common_words of
        their documents), as written in `text`, each once, in order. Only ordinary words count:
        a CV's "Paris" or "Budapest" says where they showed, not what their work is about."""
        shared, seen = [], []
        for word, lower in words(text):
            # one form per word: "Sounds" then "sound" is listed once (the first form found)
            if any(same_word(lower, s) for s in seen) or not self.is_specific(lower):
                continue
            if any(same_word(lower, a) for a in artist):
                shared.append(word)
                seen.append(lower)
        return shared


def in_sentence(sentence: str, shared: list[str]) -> list[str]:
    """The words of `sentence` that match one of the shared words, as written there (to highlight)."""
    keys = [w.lower() for w in shared]
    found = []
    for word, lower in words(sentence):
        if any(same_word(lower, k) for k in keys) and word not in found:
            found.append(word)
    return found


def best_sentence(sentences: list[str], shared: list[str]) -> str | None:
    """The sentence holding the most shared words (the first one on a tie); None if none holds any."""
    best, most = None, 0
    for sentence in sentences:
        count = len(in_sentence(sentence, shared))
        if count > most:
            best, most = sentence, count
    return best


# a shorter "sentence" of the call is a fragment or a heading ("Deadline: soon."), which explains nothing
MIN_CALL_SENTENCE_WORDS = 5


def call_sentences(opp: ProcessedOpportunity) -> list[str]:
    """The sentences of a call's description, in order (the card shows the title, not these)."""
    return [s for s in split_into_chunks(opp.description_en or "") if len(s.split()) >= MIN_CALL_SENTENCE_WORDS]


class ArtistText:
    """The artist's documents as the explanation reads them, prepared once per request:
    `documents` is [(file name, text)], the text being what ranks them (their suggest_query passages)."""

    def __init__(self, documents: list[tuple[str, str]]):
        self.words = common_words("\n".join(text for _, text in documents))
        self.sentences = [(name, sentence) for name, text in documents for sentence in clean_sentences(text)]


@dataclass
class Explanation:
    shared: list[str]                       # [] = a broad match: nothing specific in common
    call_sentence: str | None = None        # the call's sentence with the most shared words (None: only the title has them)
    call_highlight: list[str] = field(default_factory=list)   # its words to highlight, as written there
    your_sentence: str | None = None        # the artist's sentence with the most shared words
    your_highlight: list[str] = field(default_factory=list)
    your_document: str | None = None        # the file it comes from


def explain(explainer: Explainer, artist: ArtistText, opp: ProcessedOpportunity) -> Explanation:
    """What a call and the artist's documents have in common (module docstring)."""
    shared = explainer.shared_words(artist.words, call_text(opp))
    if not shared:
        return Explanation(shared=[])
    call_sentence = best_sentence(call_sentences(opp), shared)
    # the artist's sentence holding the most shared words, over all their documents (first one on a tie)
    yours, most = None, 0
    for name, sentence in artist.sentences:
        if (count := len(in_sentence(sentence, shared))) > most:
            yours, most = (name, sentence), count
    return Explanation(
        shared=shared, call_sentence=call_sentence,
        call_highlight=in_sentence(call_sentence, shared) if call_sentence else [],
        your_sentence=yours[1] if yours else None,
        your_highlight=in_sentence(yours[1], shared) if yours else [],
        your_document=yours[0] if yours else None)
