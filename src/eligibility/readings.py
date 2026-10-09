"""
OpenArt — what one classified sentence says: one reading (label, polarity,
value) per requirement it states. Used by scripts/extract_constraints.py.

The multi-label classifier can give a sentence several labels. Each label
becomes its own reading, with the polarity and value of THAT label: in
"Applicants must be resident in Belgium, regardless of nationality",
RESIDENCE REQUIRES Belgium and NATIONALITY WAIVES.

One exception: NATIONALITY and RESIDENCE both required in one sentence are
read as ONE requirement, under the more probable of the two labels:

    "Austrian citizenship or permanent residence in Austria"
    -> one reading, value {"countries": ["AT"], "nationality_or_residence": True}

That is how such a sentence was always read (values.py marks the value as
"nationality or residence" when it names both) and reviewed (one review row
per sentence). Two readings would duplicate the same check and, worse, one of
them would have no review row and turn into a needless CHECK. The cost: a
sentence requiring BOTH ("a national and resident of ...") is read as either,
which can only make the engine more lenient, never reject someone wrongly.
"""

from dataclasses import dataclass

from src.eligibility.polarity import WAIVES, polarity
from src.eligibility.values import parse_value

GEO = ("NATIONALITY", "RESIDENCE")


@dataclass
class Reading:
    label: str
    polarity: str
    value: dict | None  # None for a waiver (nothing to check) or when the parser wasn't sure


def sentence_readings(text: str, heading: str | None, labels: list[str],
                      probabilities: dict[str, float]) -> list[Reading]:
    """One reading per predicted label (most probable first), geo pair merged as described above."""
    directions = {label: polarity(text, heading, label) for label in labels}
    required_geo = [label for label in GEO if label in labels and directions[label] != WAIVES]
    if len(required_geo) == 2:
        dropped = min(required_geo, key=lambda label: probabilities[label])
        labels = [label for label in labels if label != dropped]
    return [Reading(label=label, polarity=directions[label],
                    value=None if directions[label] == WAIVES else parse_value(label, text))
            for label in labels]
