"""
OpenArt — structured extraction for funding/application_fee.

Both fields are free text (currencies, per-month vs. total, multi-part
packages described in full sentences - "Travel allowance €400 (€800
over 5,000 km) Daily allowance €30/day Accommodation on site
Mentorship") that a controlled vocabulary alone (canonicalize.py's
approach) would flatten to a category and lose the amount entirely -
see workflow.MD. This module extracts structure instead: a category AND
an amount/currency/period per distinct thing being offered.

Per-ROW, not per-distinct-value: unlike discipline/country, `funding`
values barely repeat (282 of 294 non-null values are already distinct),
so batching by distinct value the way canonicalize.py does wouldn't
save meaningful cost here. Extracts BATCH_SIZE rows per LLM call instead
(a numbered list, same mechanism as canonicalize.py's batches) to keep
the call count manageable without needing a distinct-value cache.

Two separate schemas, not one shared one - `funding` is naturally
multi-component (FundingComponent, a list - see
src/models/processed_opportunity.py); `application_fee` almost never
is, and additionally needs a has_fee signal that funding doesn't (a
stated "no fee" is meaningfully different from funding's "nothing
offered", which just wouldn't produce a component).

Numbers are a higher-risk extraction target than a category label -
confirmed on this corpus: many European/Nordic-language values use "."
as a thousands separator and "," as a decimal ("200.000,- Ft" is 200,000
Forint, not 200), and some values genuinely have no amount at all (25%
of `funding` values contain no digit whatsoever - pure prose like "This
call is for a paid residency"). The prompts below say this explicitly.
As a second, deterministic line of defense (not a replacement for
getting the prompt right - a check on top of it), ground_check() below
verifies every extracted amount's digits actually appear somewhere in
the source text, and logs (doesn't silently drop) anything that
doesn't - a cheap way to catch an outright hallucinated number before
it ends up in a "very appealing" product display.

Usage: uv run python -m src.processing.extract_funding
"""

import os
import re
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(REPO_ROOT)
load_dotenv(os.path.join(REPO_ROOT, ".env"))

from src.collectors.jsonl import load_jsonl, write_jsonl  # noqa: E402
from src.models.processed_opportunity import FundingComponent, ProcessedOpportunity  # noqa: E402

PROCESSED_PATH = os.path.join(REPO_ROOT, "data", "processed", "opportunities.jsonl")
MODEL = "gpt-5.4-mini"
BATCH_SIZE = 15  # rows per LLM call - funding text can be long, keep prompts a reasonable size

CANONICAL_FUNDING_CATEGORIES = [
    "Grant/Stipend",
    "Travel Support",
    "Accommodation/Housing",
    "Materials/Production Costs",
    "Mentorship/Training",
    "Exhibition/Presentation Support",
    "Fee Waiver",
    "Other/Unspecified Support",
]

_NUMBER_CONVENTION_NOTE = (
    "Interpret numbers using the SOURCE LANGUAGE's own convention, not "
    "English's - many European/Nordic languages use '.' as a thousands "
    "separator and ',' as a decimal separator (e.g. Hungarian "
    "'200.000,- Ft' means two hundred thousand Forint, not two hundred). "
    "Sanity-check the resulting number against what's plausible for the "
    "category (a monthly stipend of 200 is implausible for most "
    "currencies; 200,000 is far more plausible for HUF, for instance)."
)

# A percentage ("up to 100% of costs covered") is a reimbursement RATE,
# not a currency amount - confirmed once in the corpus
# (mondriaan_fund_8e2af8800941: "a maximum grant of 40% of the estimated
# value", no absolute figure at all) where the model put "%" in
# `currency` rather than leaving amount/currency null, since nothing
# in the prompt told it not to. `category`'s own vocabulary was already
# enforced by filtering the response, below; `period` and `currency`
# get the same treatment here - anything outside these fixed sets is
# nulled out (amount + currency together, since an amount without a
# valid currency isn't independently useful) rather than left to leak
# an invented value into the data. Confirmed narrow in practice: only 1
# currency violation and 5 period violations (of "per person"/"per
# 4-hour shift"/"per academic year"/"per hour", vs. the 5 periods
# below) across the whole corpus - precise but non-conforming, not
# wrong, still worth enforcing for a consistent product-facing schema.
_VALID_PERIODS = {"one-time", "per month", "per week", "per day", "per year"}
_VALID_CURRENCY = re.compile(r"^[A-Z]{3}$")


def _validate_component(c: FundingComponent) -> FundingComponent:
    if c.currency is not None and not _VALID_CURRENCY.match(c.currency):
        c = c.model_copy(update={"amount_min": None, "amount_max": None, "currency": None})
    if c.period is not None and c.period not in _VALID_PERIODS:
        c = c.model_copy(update={"period": None})
    return c


def _validate_fee(item: "FeeItem") -> "FeeItem":
    if item.currency is not None and not _VALID_CURRENCY.match(item.currency):
        item = item.model_copy(update={"amount_min": None, "amount_max": None, "currency": None})
    return item


class FundingItem(BaseModel):
    index: int
    components: list[FundingComponent]


class FundingBatch(BaseModel):
    items: list[FundingItem]


class FeeItem(BaseModel):
    index: int
    has_fee: bool
    amount_min: float | None = None
    amount_max: float | None = None
    currency: str | None = None
    note: str | None = None


class FeeBatch(BaseModel):
    items: list[FeeItem]


def extract_funding_batch(client: OpenAI, texts: list[str]) -> dict[int, list[FundingComponent]]:
    """One LLM call: structured extraction for up to BATCH_SIZE `funding` values."""
    if not texts:
        return {}

    numbered = "\n\n".join(f"{i}: {t}" for i, t in enumerate(texts))
    vocab_list = "\n".join(f"- {label}" for label in CANONICAL_FUNDING_CATEGORIES)
    response = client.chat.completions.parse(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "Each numbered value is the 'funding' field of an "
                    "arts/culture open call - free text describing what "
                    "financial or in-kind support is offered, possibly not in "
                    "English (detect the language per item). Extract every "
                    "DISTINCT thing being offered as one item in "
                    "`components` (often more than one - e.g. a travel "
                    "allowance AND a daily allowance AND on-site "
                    "accommodation are three separate components, not one):\n"
                    f"- category: exactly one of:\n{vocab_list}\n"
                    "- amount_min / amount_max: the numeric amount for this "
                    "component, if any is stated. Same value for both if it's "
                    "a fixed amount; amount_max higher than amount_min for an "
                    "explicit range or an 'up to X' cap. Leave both null if "
                    "no number applies to this component (e.g. 'mentorship', "
                    "'accommodation on site' with no figure given).\n"
                    "- currency: the ISO 4217 3-letter code (EUR, NOK, DKK, "
                    "SEK, HUF, GBP, USD, ...) for the amount given, or null "
                    "iff amount_min is null. NEVER GUESS OR DEFAULT THIS - "
                    "read it directly off the symbol/word actually in the "
                    "text: '€'/'euro'/'eur' -> EUR, '£'/'pund' -> GBP, "
                    "'$' -> USD only if the surrounding text is itself in "
                    "English with no other currency cue (many currencies use "
                    "'$' - if the text is otherwise non-English or "
                    "non-US-context, don't default to USD), 'kr'/'kroner' -> "
                    "NOK/DKK/SEK per the source language, 'Ft'/'forint' -> "
                    "HUF, 'zł'/'zloty' -> PLN. Every currency in this corpus "
                    "so far has been explicitly given via a symbol or word in "
                    "the source text - if you can't find one, leave "
                    "amount_min/amount_max/currency null rather than "
                    "guessing a currency that isn't actually there.\n"
                    "A PERCENTAGE (e.g. 'covers up to 40% of costs', with no "
                    "absolute figure given) is a rate, not a currency amount "
                    "- leave amount_min/amount_max/currency all null for it "
                    "and put the percentage in `note` instead.\n"
                    "- period: one of 'one-time', 'per month', 'per week', "
                    "'per day', 'per year', or null if unclear, not "
                    "applicable, or none of these five fit precisely (do "
                    "not invent a period outside this list - fall back to "
                    "null and use `note` for the specific timeframe if it "
                    "matters).\n"
                    "- note: a short note ONLY if something doesn't fit "
                    "cleanly (e.g. domestic vs. international rates differ) "
                    "- null otherwise.\n\n"
                    f"{_NUMBER_CONVENTION_NOTE}\n\n"
                    "If a value states no support at all that's specific to "
                    "an individual applicant (e.g. it's only a general "
                    "statement about the programme's overall budget source), "
                    "return an empty components list for that item rather "
                    "than forcing one.\n\n"
                    "When a value gives BOTH an aggregate figure (a call's "
                    "total budget/pool/envelope, shared across every "
                    "recipient of that round) AND a distinct per-applicant "
                    "or per-project figure, extract ONLY the per-applicant/"
                    "per-project figure(s) as component(s) - never the "
                    "aggregate pool, since that's not what any single "
                    "applicant receives and displaying it as if it were "
                    "would mislead an artist reading it. If several distinct "
                    "per-applicant tiers/strands are given (e.g. a small/"
                    "medium/large-scale cap, or Strand A vs. Strand B), "
                    "extract EACH as its own component, not just one. Only "
                    "extract the aggregate figure itself if NO per-applicant "
                    "figure is given anywhere in the value - and in that "
                    "case, say so explicitly in `note` (e.g. 'total pool "
                    "across all recipients, no per-applicant cap stated')."
                ),
            },
            {"role": "user", "content": numbered},
        ],
        response_format=FundingBatch,
    )

    result: dict[int, list[FundingComponent]] = {}
    for item in response.choices[0].message.parsed.items:
        if 0 <= item.index < len(texts):
            result[item.index] = [
                _validate_component(c) for c in item.components if c.category in CANONICAL_FUNDING_CATEGORIES
            ]
    return result


def extract_fee_batch(client: OpenAI, texts: list[str]) -> dict[int, FeeItem]:
    """One LLM call: structured extraction for up to BATCH_SIZE `application_fee` values."""
    if not texts:
        return {}

    numbered = "\n\n".join(f"{i}: {t}" for i, t in enumerate(texts))
    response = client.chat.completions.parse(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "Each numbered value is the 'application_fee' field of "
                    "an arts/culture open call - free text about whether "
                    "applying costs money, possibly not in English. For "
                    "each:\n"
                    "- has_fee: true if a fee is required to apply, false if "
                    "the text explicitly says applying is free/no fee. "
                    "Every one of these values IS present (the field is "
                    "never blank here), so always set this - it is never "
                    "left unset.\n"
                    "- amount_min / amount_max: the fee amount, if a fee "
                    "applies and a figure is given. Same value for both if "
                    "fixed; amount_max higher for a range or tiered fee "
                    "(e.g. early-bird vs. regular). Null if has_fee is "
                    "false, or true with no figure given.\n"
                    "- currency: the ISO 4217 3-letter code, or null iff "
                    "amount_min is null.\n"
                    "- note: a short note only for something that doesn't "
                    "fit cleanly (e.g. a tiered fee schedule) - null "
                    "otherwise.\n\n"
                    f"{_NUMBER_CONVENTION_NOTE}"
                ),
            },
            {"role": "user", "content": numbered},
        ],
        response_format=FeeBatch,
    )

    result: dict[int, FeeItem] = {}
    for item in response.choices[0].message.parsed.items:
        if 0 <= item.index < len(texts):
            result[item.index] = _validate_fee(item)
    return result


_NUMBER_TOKEN = re.compile(r"\d[\d.,]*\d|\d")


def _numbers_in_text(text: str) -> set[str]:
    return {re.sub(r"[.,]", "", tok) for tok in _NUMBER_TOKEN.findall(text)}


def ground_check(amount: float, source_text: str) -> bool:
    """True iff `amount`'s digits plausibly appear somewhere in
    `source_text` - a cheap, deterministic check against an outright
    hallucinated number, not a guarantee the amount was interpreted
    correctly (a correctly-grounded number can still have the wrong
    thousands/decimal convention applied - see module docstring).
    """
    amount_str = str(int(amount)) if amount == int(amount) else str(amount).replace(".", "")
    source_numbers = _numbers_in_text(source_text)
    return any(amount_str == n or amount_str in n or n in amount_str for n in source_numbers)


def _batches(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def extract_all(processed_path: str = PROCESSED_PATH) -> dict:
    """Merges by "already has an extraction" like every other stage, not
    by id - re-running only pays for rows whose funding/application_fee
    hasn't been extracted yet, not every row with a value.

    funding_extracted_at (not "funding_components is []") is the signal
    for funding: an empty components list is itself a legitimate result
    (~9% of funding values describe nothing applicant-specific - see
    module docstring), so it can't double as "not yet processed" the
    way it would for a field where empty is never a valid outcome.
    application_fee_has_fee can double as its own signal, since a
    processed row always gets true/false there, never stays None.
    """
    records: list[ProcessedOpportunity] = load_jsonl(processed_path, ProcessedOpportunity)
    client = OpenAI()

    funding_rows = [r for r in records if r.funding and r.funding_extracted_at is None]
    fee_rows = [r for r in records if r.application_fee and r.application_fee_has_fee is None]

    funding_extracted = 0
    ungrounded_amounts = []
    for batch in _batches(funding_rows, BATCH_SIZE):
        texts = [r.funding for r in batch]
        result = extract_funding_batch(client, texts)
        for i, r in enumerate(batch):
            components = result.get(i, [])
            r.funding_components = components
            r.funding_extracted_at = datetime.now(timezone.utc)
            funding_extracted += 1
            for c in components:
                for amount in (c.amount_min, c.amount_max):
                    if amount is not None and not ground_check(amount, r.funding):
                        ungrounded_amounts.append((r.id, c.category, amount, r.funding[:80]))

    fee_extracted = 0
    for batch in _batches(fee_rows, BATCH_SIZE):
        texts = [r.application_fee for r in batch]
        result = extract_fee_batch(client, texts)
        for i, r in enumerate(batch):
            item = result.get(i)
            if item is None:
                continue
            r.application_fee_has_fee = item.has_fee
            r.application_fee_amount_min = item.amount_min
            r.application_fee_amount_max = item.amount_max
            r.application_fee_currency = item.currency
            fee_extracted += 1
            for amount in (item.amount_min, item.amount_max):
                if amount is not None and not ground_check(amount, r.application_fee):
                    ungrounded_amounts.append((r.id, "application_fee", amount, r.application_fee[:80]))

    write_jsonl(records, processed_path)

    print(f"funding: {funding_extracted} row(s) processed")
    print(f"application_fee: {fee_extracted} row(s) processed")
    if ungrounded_amounts:
        print(f"\n{len(ungrounded_amounts)} extracted amount(s) not found in their source text - review these:")
        for id_, category, amount, excerpt in ungrounded_amounts:
            print(f"  {id_} [{category}] {amount!r} not grounded in: {excerpt!r}")
    print(f"\nUpdated {len(records)} record(s) -> {processed_path}")

    return {
        "funding_extracted": funding_extracted,
        "fee_extracted": fee_extracted,
        "ungrounded": len(ungrounded_amounts),
    }


if __name__ == "__main__":
    extract_all()
