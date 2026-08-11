"""SEC Form 8-K item taxonomy.

Maps the numbered items a registrant can disclose under an 8-K to a normalized
event category and a base materiality weight (1 = routine, 5 = severe). The
codes and labels follow Item 1.01-9.01 of Form 8-K as defined in 17 CFR 249.308.
"""

from __future__ import annotations

from typing import Dict, List, NamedTuple

from secmonitor.models import EventTag


class ItemDef(NamedTuple):
    label: str
    category: str
    weight: int


# code -> (label, category, base materiality weight)
ITEM_TAXONOMY: Dict[str, ItemDef] = {
    "1.01": ItemDef("Entry into a Material Definitive Agreement", "material_agreement", 3),
    "1.02": ItemDef("Termination of a Material Definitive Agreement", "material_agreement", 3),
    "1.03": ItemDef("Bankruptcy or Receivership", "bankruptcy", 5),
    "1.04": ItemDef("Mine Safety - Reporting of Shutdowns and Patterns of Violations", "other", 1),
    "1.05": ItemDef("Material Cybersecurity Incident", "cyber", 5),
    "2.01": ItemDef("Completion of Acquisition or Disposition of Assets", "m_and_a", 4),
    "2.02": ItemDef("Results of Operations and Financial Condition", "earnings", 3),
    "2.03": ItemDef("Creation of a Direct Financial Obligation", "debt_financing", 3),
    "2.04": ItemDef("Triggering Events That Accelerate a Financial Obligation", "debt_financing", 4),
    "2.05": ItemDef("Costs Associated with Exit or Disposal Activities", "restructuring", 3),
    "2.06": ItemDef("Material Impairments", "impairment", 4),
    "3.01": ItemDef("Notice of Delisting or Failure to Satisfy a Listing Rule", "delisting", 4),
    "3.02": ItemDef("Unregistered Sales of Equity Securities", "equity_issuance", 2),
    "3.03": ItemDef("Material Modification to Rights of Security Holders", "capital_structure", 3),
    "4.01": ItemDef("Changes in Registrant's Certifying Accountant", "accountant_change", 3),
    "4.02": ItemDef("Non-Reliance on Previously Issued Financial Statements", "restatement", 5),
    "5.01": ItemDef("Changes in Control of Registrant", "control_change", 4),
    "5.02": ItemDef("Departure/Election of Directors or Officers", "leadership_change", 3),
    "5.03": ItemDef("Amendments to Articles of Incorporation or Bylaws", "governance", 2),
    "5.04": ItemDef("Temporary Suspension of Trading Under Employee Benefit Plans", "governance", 2),
    "5.05": ItemDef("Amendments to Code of Ethics / Waiver", "governance", 1),
    "5.06": ItemDef("Change in Shell Company Status", "control_change", 3),
    "5.07": ItemDef("Submission of Matters to a Vote of Security Holders", "governance", 1),
    "5.08": ItemDef("Shareholder Director Nominations", "governance", 1),
    "6.01": ItemDef("ABS Informational and Computational Material", "other", 1),
    "6.02": ItemDef("Change of Servicer or Trustee", "other", 1),
    "6.03": ItemDef("Change in Credit Enhancement or External Support", "other", 2),
    "6.04": ItemDef("Failure to Make a Required Distribution", "other", 3),
    "6.05": ItemDef("Securities Act Updating Disclosure", "other", 1),
    "7.01": ItemDef("Regulation FD Disclosure", "disclosure", 2),
    "8.01": ItemDef("Other Events", "other_material_event", 2),
    "9.01": ItemDef("Financial Statements and Exhibits", "exhibits_only", 1),
}

# Keywords scanned against filing text (case-insensitive) that bump a
# category's default read when the item code alone is ambiguous, e.g. 8.01 is
# a catch-all that frequently carries litigation or M&A-announcement news.
CATEGORY_KEYWORD_HINTS: Dict[str, List[str]] = {
    "litigation": ["lawsuit", "complaint", "litigation", "class action", "subpoena",
                   "investigation", "settlement", "sec inquiry", "doj"],
    "m_and_a": ["merger agreement", "acquire", "acquisition", "definitive agreement to purchase",
                "combine with", "tender offer"],
    "cyber": ["cybersecurity incident", "unauthorized access", "data breach", "ransomware"],
    "restatement": ["material weakness", "restate", "restatement", "non-reliance"],
    "going_concern": ["going concern", "substantial doubt"],
}


def classify_items(item_codes: List[str]) -> List[EventTag]:
    """Turn a list of raw 8-K item codes (e.g. ["5.02", "9.01"]) into EventTags."""
    tags: List[EventTag] = []
    for code in item_codes:
        code = code.strip()
        if not code:
            continue
        item = ITEM_TAXONOMY.get(code)
        if item is None:
            tags.append(EventTag(code=code, label=f"Unrecognized Item {code}", category="other", weight=2))
            continue
        tags.append(EventTag(code=code, label=item.label, category=item.category, weight=item.weight))
    return tags


def refine_catchall_category(tags: List[EventTag], text: str) -> List[EventTag]:
    """Re-bucket generic Item 8.01 / 7.01 tags using keyword hints from the filing
    body, since the item code alone doesn't distinguish litigation news from an
    M&A teaser from a routine press release."""
    if not text:
        return tags
    lowered = text.lower()
    refined = []
    for tag in tags:
        if tag.category not in ("other_material_event", "disclosure"):
            refined.append(tag)
            continue
        matched_category = None
        for category, keywords in CATEGORY_KEYWORD_HINTS.items():
            if any(kw in lowered for kw in keywords):
                matched_category = category
                break
        if matched_category:
            weight = {
                "litigation": 4,
                "m_and_a": 4,
                "cyber": 5,
                "restatement": 5,
                "going_concern": 5,
            }.get(matched_category, tag.weight)
            refined.append(EventTag(code=tag.code, label=tag.label, category=matched_category, weight=weight))
        else:
            refined.append(tag)
    return refined
