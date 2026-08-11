"""Renders a list of FilingEvents into a weekly analyst-style markdown memo."""

from __future__ import annotations

from collections import Counter
from datetime import date
from typing import List

from secmonitor.models import FilingEvent

TIER_ORDER = ["Critical", "High", "Medium", "Low", "Informational"]


def _category_label(category: str) -> str:
    return category.replace("_", " ").title()


def _event_block(event: FilingEvent) -> str:
    filing = event.filing
    item_codes = ", ".join(sorted({t.code for t in event.tags})) or "n/a"
    categories = ", ".join(sorted({_category_label(t.category) for t in event.tags})) or "Other"
    narrative_note = "" if event.source == "llm" else " _(template-generated; no LLM key configured)_"

    lines = [
        f"### {filing.company.name} ({filing.company.ticker}) — {categories}",
        f"**Filed:** {filing.filing_date.isoformat()}  |  **Items:** {item_codes}  |  "
        f"**Materiality:** {event.materiality.level} ({event.materiality.score}/5)",
        "",
        f"**What happened:** {event.what_happened}",
        "",
        f"**Why it matters:** {event.why_it_matters}",
        "",
        f"**Valuation / risk / thesis impact:** {event.thesis_impact}{narrative_note}",
        "",
        f"**Materiality rationale:** {event.materiality.rationale}",
        "",
        f"**Source:** [SEC EDGAR filing]({filing.filing_index_url})",
    ]
    return "\n".join(lines)


def render_weekly_memo(events: List[FilingEvent], week_start: date, week_end: date, sector: str = "") -> str:
    header_sector = f" — {sector} Sector" if sector else ""
    out = [
        f"# Weekly SEC 8-K Monitor{header_sector}",
        f"**Coverage window:** {week_start.isoformat()} to {week_end.isoformat()}",
        "",
    ]

    if not events:
        out.append("No material 8-K filings were observed for the tracked universe in this window.")
        return "\n".join(out)

    companies_involved = sorted({e.filing.company.ticker for e in events})
    category_counts = Counter(_category_label(e.primary_category) for e in events)
    category_summary = ", ".join(f"{label} ({count})" for label, count in category_counts.most_common())

    out += [
        "## Summary",
        f"- **Filings observed:** {len(events)}",
        f"- **Companies involved:** {len(companies_involved)} ({', '.join(companies_involved)})",
        f"- **Event mix:** {category_summary}",
        "",
    ]

    by_level = {level: [] for level in TIER_ORDER}
    for event in events:
        by_level.setdefault(event.materiality.level, []).append(event)

    for level in TIER_ORDER:
        tier_events = by_level.get(level, [])
        if not tier_events:
            continue
        out.append(f"## {level} Materiality")
        out.append("")
        for event in tier_events:
            out.append(_event_block(event))
            out.append("")
            out.append("---")
            out.append("")

    return "\n".join(out).rstrip() + "\n"
