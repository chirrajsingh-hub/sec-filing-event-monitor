"""Taxonomy of SEC Form 8-K "Item" disclosure codes.

The SEC's 8-K form is a checklist: a filer marks which numbered Items its
disclosure covers (e.g. "2.02" = quarterly results, "5.02" = an officer or
director departure/election). The submissions API returns those item codes
directly as a comma-separated string per filing, so classifying a filing's
*kind* of event doesn't require parsing the filing text at all -- only
scoring how material or urgent it is benefits from reading further, which is
what `secmonitor.scoring` does with the keyword rules below.

Reference: 17 CFR 249.308, SEC 8-K General Instructions.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EventCategory:
    code: str
    label: str
    description: str
    base_materiality: int  # 1-10, "how much could this move the fundamental thesis"
    base_urgency: int  # 1-10, "how quickly does the market need to react"


# Item 9.01 (exhibits) and 7.01 (Reg FD) are administrative/procedural on
# their own -- they almost always ride alongside a substantive item and
# shouldn't set the headline category for a filing.
ADMINISTRATIVE_CODES = frozenset({"7.01", "9.01"})

ITEM_TAXONOMY: dict[str, EventCategory] = {
    "1.01": EventCategory(
        "1.01", "Material Agreement",
        "Entry into a material definitive agreement -- could be an M&A "
        "deal, a credit facility, or a commercial partnership; the "
        "specific flavor is disambiguated by keyword rules.",
        base_materiality=6, base_urgency=5,
    ),
    "1.02": EventCategory(
        "1.02", "Agreement Termination",
        "Termination of a material definitive agreement.",
        base_materiality=5, base_urgency=5,
    ),
    "1.03": EventCategory(
        "1.03", "Bankruptcy / Receivership",
        "Bankruptcy or receivership filing.",
        base_materiality=10, base_urgency=10,
    ),
    "1.05": EventCategory(
        "1.05", "Cybersecurity Incident",
        "Material cybersecurity incident (Item 1.05, effective Dec 2023).",
        base_materiality=9, base_urgency=9,
    ),
    "2.01": EventCategory(
        "2.01", "M&A Completion",
        "Completion of an acquisition or disposition of a significant "
        "amount of assets.",
        base_materiality=9, base_urgency=6,
    ),
    "2.02": EventCategory(
        "2.02", "Earnings / Results of Operations",
        "Results of operations and financial condition -- typically a "
        "quarterly or annual earnings release.",
        base_materiality=6, base_urgency=4,
    ),
    "2.03": EventCategory(
        "2.03", "Debt Financing",
        "Creation of a direct financial obligation -- a new credit "
        "facility, term loan, or notes offering.",
        base_materiality=6, base_urgency=4,
    ),
    "2.04": EventCategory(
        "2.04", "Obligation Acceleration",
        "A triggering event that accelerates or increases a financial "
        "obligation -- often a covenant breach.",
        base_materiality=7, base_urgency=7,
    ),
    "2.05": EventCategory(
        "2.05", "Restructuring",
        "Costs associated with exit or disposal activities -- layoffs, "
        "plant closures, restructuring charges.",
        base_materiality=6, base_urgency=5,
    ),
    "2.06": EventCategory(
        "2.06", "Material Impairment",
        "Material impairment of assets or goodwill.",
        base_materiality=7, base_urgency=5,
    ),
    "3.01": EventCategory(
        "3.01", "Delisting Notice",
        "Notice of delisting or failure to satisfy an exchange listing "
        "rule.",
        base_materiality=8, base_urgency=8,
    ),
    "3.02": EventCategory(
        "3.02", "Unregistered Equity Sale",
        "Unregistered sale of equity securities.",
        base_materiality=4, base_urgency=3,
    ),
    "3.03": EventCategory(
        "3.03", "Security Holder Rights Change",
        "Material modification to the rights of security holders.",
        base_materiality=4, base_urgency=3,
    ),
    "4.01": EventCategory(
        "4.01", "Auditor Change",
        "Change in the registrant's certifying accountant.",
        base_materiality=6, base_urgency=5,
    ),
    "4.02": EventCategory(
        "4.02", "Restatement / Non-Reliance",
        "Non-reliance on previously issued financial statements or a "
        "related audit report -- a restatement signal.",
        base_materiality=9, base_urgency=8,
    ),
    "5.01": EventCategory(
        "5.01", "Change in Control",
        "Change in control of the registrant.",
        base_materiality=9, base_urgency=6,
    ),
    "5.02": EventCategory(
        "5.02", "Leadership Change",
        "Departure or election of directors or officers.",
        base_materiality=6, base_urgency=5,
    ),
    "5.03": EventCategory(
        "5.03", "Bylaws / Charter Amendment",
        "Amendments to articles of incorporation or bylaws.",
        base_materiality=3, base_urgency=2,
    ),
    "5.07": EventCategory(
        "5.07", "Shareholder Vote Results",
        "Submission of matters to a vote of security holders.",
        base_materiality=3, base_urgency=2,
    ),
    "7.01": EventCategory(
        "7.01", "Reg FD Disclosure",
        "Regulation FD disclosure -- often investor-day slides or "
        "guidance updates.",
        base_materiality=4, base_urgency=3,
    ),
    "8.01": EventCategory(
        "8.01", "Other Material Events",
        "Catch-all item -- frequently used for litigation, regulatory "
        "inquiries, and other events without a dedicated item number.",
        base_materiality=5, base_urgency=4,
    ),
    "9.01": EventCategory(
        "9.01", "Financial Statements & Exhibits",
        "Exhibits filed with the 8-K -- procedural, not a standalone "
        "event.",
        base_materiality=1, base_urgency=1,
    ),
}


def normalize_items(items: str | list[str]) -> list[str]:
    """Turn the API's comma-separated item string (or a list) into a clean list."""
    if isinstance(items, str):
        raw = items.split(",")
    else:
        raw = items
    return [code.strip() for code in raw if code and code.strip()]


def item_categories(items: str | list[str]) -> list[EventCategory]:
    """Resolve each item code on a filing to its EventCategory, skipping unknown codes."""
    return [
        ITEM_TAXONOMY[code]
        for code in normalize_items(items)
        if code in ITEM_TAXONOMY
    ]


def primary_category(items: str | list[str]) -> EventCategory:
    """Pick the single category that should headline a filing.

    A filing often bundles a substantive item with an administrative one
    (e.g. "5.02,9.01"). The headline should be the most material
    *non-administrative* item; fall back to whatever is present (even if
    purely administrative) rather than raising, since a filing with only
    9.01 is unusual but not invalid.
    """
    categories = item_categories(items)
    if not categories:
        raise ValueError(f"No recognized 8-K item codes in {items!r}")

    substantive = [c for c in categories if c.code not in ADMINISTRATIVE_CODES]
    pool = substantive or categories
    return max(pool, key=lambda c: c.base_materiality)
