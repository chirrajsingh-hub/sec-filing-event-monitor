"""Materiality / urgency scoring for a classified 8-K filing.

The score is a simple, explainable heuristic rather than a black box: it
starts from the highest-weight event tag on the filing, adds a small bump
when multiple material items stack in one filing, and adds another bump when
the filing text itself contains high-severity language. Every score carries
a plain-English rationale so a reader can sanity-check it against the source
filing rather than trusting a bare number.
"""

from __future__ import annotations

from typing import List, Optional

from secmonitor.models import EventTag, MaterialityScore

LEVELS = {
    1: "Informational",
    2: "Low",
    3: "Medium",
    4: "High",
    5: "Critical",
}

SEVERE_KEYWORDS = [
    "material weakness", "going concern", "substantial doubt", "restate",
    "bankruptcy", "chapter 11", "data breach", "ransomware", "class action",
    "sec investigation", "doj investigation", "resign", "terminated for cause",
]


def score_filing(tags: List[EventTag], text: Optional[str] = None) -> MaterialityScore:
    if not tags:
        return MaterialityScore(score=1, level=LEVELS[1], rationale="No classifiable items on the filing.")

    base_tag = max(tags, key=lambda t: t.weight)
    score = base_tag.weight
    reasons = [f"Item {base_tag.code} ({base_tag.label}) carries a base weight of {base_tag.weight}/5."]

    material_tags = [t for t in tags if t.weight >= 3 and t.code != base_tag.code]
    if len(material_tags) >= 1:
        score = min(5, score + 1)
        codes = ", ".join(sorted({t.code for t in material_tags}))
        reasons.append(f"Filing stacks additional material items ({codes}), raising combined significance.")

    if text:
        lowered = text.lower()
        hits = sorted({kw for kw in SEVERE_KEYWORDS if kw in lowered})
        if hits:
            score = min(5, score + 1)
            reasons.append(f"Filing text contains high-severity language: {', '.join(hits[:3])}.")

    score = max(1, min(5, score))
    return MaterialityScore(score=score, level=LEVELS[score], rationale=" ".join(reasons))
