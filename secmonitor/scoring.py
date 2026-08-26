"""Rule-based materiality/urgency scoring for a classified 8-K filing.

This is deliberately transparent rather than an ML/LLM black box: the score
is the item-code base weight (see `events.ITEM_TAXONOMY`) plus a handful of
documented keyword adjustments, each of which is recorded in a
human-readable rationale so a reader can see exactly why a filing scored
the way it did. That's the right trade for a repeatable analyst workflow --
a score you can't explain in a memo isn't useful in one.

Limitation, stated plainly: keyword matching is a blunt instrument. It will
miss negation ("did not restate"), sarcasm, and phrasing outside the
keyword list, and it has no notion of the company's size or the deal's
dollar magnitude. Treat scores as a triage signal -- "read this filing
first" -- not a verdict.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from secmonitor.events import EventCategory, item_categories, primary_category

MIN_SCORE = 1
MAX_SCORE = 10


@dataclass(frozen=True)
class KeywordRule:
    keywords: tuple[str, ...]
    materiality_delta: int
    urgency_delta: int
    note: str
    # Restrict the rule to filings whose primary item is one of these codes,
    # or leave empty to apply regardless of item code.
    applies_to: tuple[str, ...] = ()


KEYWORD_RULES: list[KeywordRule] = [
    KeywordRule(
        ("going concern",), materiality_delta=3, urgency_delta=2,
        note='"going concern" language present',
    ),
    KeywordRule(
        ("chapter 11", "chapter 7", "bankruptcy"), materiality_delta=2, urgency_delta=2,
        note="bankruptcy language present outside Item 1.03",
    ),
    KeywordRule(
        ("material weakness", "restate", "restatement"),
        materiality_delta=2, urgency_delta=1,
        note="restatement / material-weakness language",
    ),
    KeywordRule(
        ("data breach", "unauthorized access", "ransomware", "threat actor"),
        materiality_delta=1, urgency_delta=2,
        note="incident-severity language in a cybersecurity disclosure",
    ),
    KeywordRule(
        ("merger agreement", "definitive agreement to acquire", "acquisition of",
         "agreed to acquire", "agreed to be acquired"),
        materiality_delta=2, urgency_delta=1,
        note="M&A-flavored material agreement",
        applies_to=("1.01",),
    ),
    KeywordRule(
        ("credit agreement", "senior notes", "term loan", "notes due", "revolving credit"),
        materiality_delta=0, urgency_delta=0,
        note="debt-financing-flavored material agreement",
        applies_to=("1.01",),
    ),
    KeywordRule(
        ("chief executive officer", "chief financial officer", " ceo ", " cfo "),
        materiality_delta=2, urgency_delta=1,
        note="C-suite (CEO/CFO) role involved, not a lower officer",
        applies_to=("5.02",),
    ),
    KeywordRule(
        ("resign", "resignation", "terminated", "removed"),
        materiality_delta=0, urgency_delta=1,
        note="departure was abrupt/involuntary rather than a planned transition",
        applies_to=("5.02",),
    ),
    KeywordRule(
        ("lowers guidance", "cuts guidance", "withdraws guidance", "guidance cut",
         "misses", "shortfall", "preliminary results"),
        materiality_delta=2, urgency_delta=2,
        note="unscheduled or negative earnings signal",
        applies_to=("2.02",),
    ),
    KeywordRule(
        ("lawsuit", "litigation", "subpoena", "investigation", "sec inquiry",
         "class action", "ftc", "doj"),
        materiality_delta=2, urgency_delta=1,
        note="litigation/regulatory language under the Item 8.01 catch-all",
        applies_to=("8.01",),
    ),
]


@dataclass(frozen=True)
class Score:
    materiality: int
    urgency: int
    rationale: list[str] = field(default_factory=list)

    @property
    def combined(self) -> int:
        return self.materiality + self.urgency

    def rationale_text(self) -> str:
        return "; ".join(self.rationale) if self.rationale else "item-code baseline only"


def _clamp(value: int) -> int:
    return max(MIN_SCORE, min(MAX_SCORE, value))


def score_filing(items: str | list[str], headline: str = "", snippet: str = "") -> Score:
    """Score a filing's materiality and urgency from its item codes and text.

    `headline`/`snippet` are whatever free text is available for the filing
    (in offline/fixture mode, a hand-written summary; in live mode,
    best-effort extracted text -- see `secmonitor.edgar_client`). Passing
    empty strings still produces a valid score from the item-code baseline
    alone.
    """
    categories: list[EventCategory] = item_categories(items)
    if not categories:
        raise ValueError(f"No recognized 8-K item codes in {items!r}")

    headline_cat = primary_category(items)
    materiality = headline_cat.base_materiality
    urgency = headline_cat.base_urgency
    rationale = [f"Item {headline_cat.code} ({headline_cat.label}) baseline "
                 f"{headline_cat.base_materiality}/{headline_cat.base_urgency}"]

    substantive_codes = {c.code for c in categories}
    if len(substantive_codes - {"7.01", "9.01"}) > 1:
        materiality += 1
        rationale.append("multiple substantive items bundled in one filing (+1 materiality)")

    text = f"{headline} {snippet}".lower()
    for rule in KEYWORD_RULES:
        if rule.applies_to and headline_cat.code not in rule.applies_to:
            continue
        if any(kw in text for kw in rule.keywords):
            if rule.materiality_delta or rule.urgency_delta:
                materiality += rule.materiality_delta
                urgency += rule.urgency_delta
                rationale.append(
                    f"{rule.note} "
                    f"(+{rule.materiality_delta} materiality, +{rule.urgency_delta} urgency)"
                )
            else:
                rationale.append(rule.note)

    return Score(materiality=_clamp(materiality), urgency=_clamp(urgency), rationale=rationale)
