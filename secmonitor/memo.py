"""Render a PipelineResult into a weekly, analyst-memo-style Markdown document.

Layout: a header with coverage stats, a highlights section for the
highest-scored events, then every event grouped by category, then a
methodology appendix that spells out the scoring rubric and this project's
known limitations. The appendix isn't boilerplate -- it's the difference
between "a script that prints scores" and something a reader can actually
trust a specific number from, because they can see exactly how it was
computed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from secmonitor.news_client import NewsItem
    from secmonitor.pipeline import PipelineResult, ScoredEvent

NEWS_SENTIMENT_MARKERS = {
    "Bearish": "▼", "Somewhat-Bearish": "▼",
    "Neutral": "•",
    "Somewhat-Bullish": "▲", "Bullish": "▲",
}

HIGHLIGHT_THRESHOLD = 8  # materiality >= this shows up in the Highlights section

# Rule-based "why it matters" / "watch next" scaffolding per item code. This
# is intentionally generic and templated, not a per-company financial model
# -- it's the analyst prompt a human (or a further research step) would
# start from, not a finished thesis.
CATEGORY_COMMENTARY: dict[str, dict[str, str]] = {
    "1.01": {
        "why": "A new material agreement can change the revenue mix, cost "
               "structure, or competitive position -- direction depends on "
               "whether this is a growth bet (partnership, acquisition) or "
               "a defensive one (financing, litigation settlement).",
        "watch": "Read the actual agreement terms: deal size relative to "
                 "market cap, financing structure, exclusivity, and any "
                 "termination fee that signals how committed both sides are.",
    },
    "1.02": {
        "why": "Terminating a material agreement removes whatever revenue, "
               "supply, or strategic optionality it provided.",
        "watch": "Why was it terminated -- mutual, for cause, or a "
                 "walk-away -- and whether a replacement arrangement exists.",
    },
    "1.03": {
        "why": "Bankruptcy or receivership is typically a near-total loss "
               "for equity holders and a recovery question for creditors.",
        "watch": "Capital structure and where equity sits in the waterfall; "
                 "whether this is Chapter 11 (reorganization) or Chapter 7 "
                 "(liquidation).",
    },
    "1.05": {
        "why": "A material cybersecurity incident carries direct remediation "
               "cost, potential customer/data liability, and reputational "
               "risk that can outlast the immediate disclosure.",
        "watch": "Scope of data/systems affected, whether operations were "
                 "disrupted, and any follow-on regulatory or class-action "
                 "exposure.",
    },
    "2.01": {
        "why": "A completed acquisition or disposition directly changes the "
               "asset base, and the price paid sets the bar the deal has to "
               "clear to be accretive.",
        "watch": "Purchase price vs. the target's revenue/EBITDA, financing "
                 "mix (cash/debt/equity), and integration risk.",
    },
    "2.02": {
        "why": "Earnings results and forward guidance are usually the "
               "single biggest near-term driver of the stock.",
        "watch": "Guidance direction relative to consensus, not just the "
                 "reported quarter; a beat with lowered guidance often "
                 "trades worse than a modest miss with raised guidance.",
    },
    "2.03": {
        "why": "New debt changes leverage and interest expense, and the use "
               "of proceeds signals whether management sees a growth "
               "opportunity or a liquidity need.",
        "watch": "Coupon/rate relative to existing debt, covenants, and "
                 "whether proceeds fund capex, refinancing, or buybacks.",
    },
    "2.04": {
        "why": "An acceleration trigger (often a covenant breach) signals "
               "financial stress and can force asset sales or refinancing "
               "on unfavorable terms.",
        "watch": "Which obligation was triggered and whether a waiver or "
                 "amendment is already in place.",
    },
    "2.05": {
        "why": "Restructuring charges trade near-term cash cost for a "
               "leaner cost base -- whether that's a positive depends on "
               "whether the cuts hit growth capacity or genuine slack.",
        "watch": "Cash vs. non-cash portion of the charge, expected "
                 "annualized savings, and what capacity is being removed.",
    },
    "2.06": {
        "why": "An impairment is a non-cash accounting write-down, but it's "
               "a lagging admission that a past investment's economics "
               "deteriorated -- worth checking what else in the portfolio "
               "shares that thesis.",
        "watch": "Which reporting unit or asset class was written down and "
                 "whether it maps to a business the company still relies on.",
    },
    "3.01": {
        "why": "A delisting notice threatens the stock's liquidity and "
               "index eligibility, both of which affect the shareholder "
               "base independent of the underlying business.",
        "watch": "Which listing standard was breached (price, market cap, "
                 "governance) and the cure period.",
    },
    "3.02": {
        "why": "An unregistered equity sale is usually small relative to "
               "the float but is a dilution data point worth tracking "
               "cumulatively.",
        "watch": "Size of the issuance relative to shares outstanding and "
                 "the counterparty (insider, lender, or note conversion).",
    },
    "3.03": {
        "why": "Changes to security-holder rights (e.g. a poison pill) "
               "usually signal the board is defending against something "
               "specific.",
        "watch": "What prompted the change -- an activist stake, a hostile "
                 "approach, or routine governance cleanup.",
    },
    "4.01": {
        "why": "An auditor change is routine most of the time, but an "
               "unscheduled dismissal (vs. a planned rotation) is a "
               "governance flag worth a second look.",
        "watch": "Whether the filing discloses any disagreement with the "
                 "outgoing auditor on accounting matters.",
    },
    "4.02": {
        "why": "Non-reliance on prior financials means the numbers the "
               "market was pricing the stock on were wrong -- this is one "
               "of the highest-signal disclosures in the whole taxonomy.",
        "watch": "Which periods and line items are affected, whether "
                 "cash/revenue economics change or it's presentation-only, "
                 "and whether it points to a broader controls problem.",
    },
    "5.01": {
        "why": "A change in control changes who is actually making capital "
               "allocation decisions going forward.",
        "watch": "Who the new controlling party is and whether a tender "
                 "offer or squeeze-out for remaining shares is likely.",
    },
    "5.02": {
        "why": "Leadership changes at the CEO/CFO level can signal a "
               "strategy shift, and abrupt (vs. planned) departures often "
               "precede other bad news.",
        "watch": "Planned succession vs. abrupt exit, the successor's "
                 "background, and whether other executives depart soon "
                 "after.",
    },
    "5.03": {
        "why": "Bylaw/charter amendments are usually procedural but "
               "occasionally bundle in governance changes worth noting.",
        "watch": "Whether the amendment affects shareholder voting power "
                 "or board structure.",
    },
    "5.07": {
        "why": "Annual-meeting vote results are mostly routine, but a "
               "surprisingly low approval margin on say-on-pay or a "
               "director election is a real signal of shareholder "
               "dissatisfaction.",
        "watch": "Vote margins, not just outcomes -- a director elected "
                 "with 55% support is a different story than one at 98%.",
    },
    "7.01": {
        "why": "Reg FD disclosures are how companies share material "
               "information (investor-day slides, updated guidance) "
               "broadly and simultaneously.",
        "watch": "Whatever was furnished -- this item alone has no content "
                 "of its own.",
    },
    "8.01": {
        "why": "This is the catch-all item, most often used for "
               "litigation, regulatory inquiries, or events without a "
               "dedicated item number -- materiality varies enormously.",
        "watch": "Read the actual text; this item's base score is "
                 "deliberately conservative because it covers everything "
                 "from a routine press release to a major lawsuit.",
    },
    "9.01": {
        "why": "Exhibits only -- not an event on its own.",
        "watch": "Check what the exhibit actually is; it's usually tied to "
                 "another item on the same filing.",
    },
}


def _fmt_score_bar(score: int, width: int = 10) -> str:
    filled = "#" * score
    empty = "." * (width - score)
    return f"`{filled}{empty}` {score}/10"


def _event_block(event: "ScoredEvent", heading_level: int = 3) -> str:
    hashes = "#" * heading_level
    commentary = CATEGORY_COMMENTARY.get(
        event.primary_category.code,
        {"why": "See the filing for details.", "watch": "See the filing for details."},
    )
    items_str = ", ".join(f"Item {c}" for c in event.items)
    lines = [
        f"{hashes} {event.company} ({event.ticker}) -- {event.primary_category.label}",
        "",
        f"- **Filed:** {event.filing_date.isoformat()}  ·  **{items_str}**",
        f"- **Materiality:** {_fmt_score_bar(event.materiality)}"
        f"   **Urgency:** {_fmt_score_bar(event.urgency)}",
        f"- **What happened:** {event.headline}",
    ]
    if event.snippet:
        lines.append(f"- **From the filing:** {event.snippet}")
    lines += [
        f"- **Why it matters:** {commentary['why']}",
        f"- **Watch next:** {commentary['watch']}",
        f"- **Score rationale:** {event.rationale_joined}",
        f"- **Source:** [EDGAR filing]({event.edgar_url}) "
        f"(accession {event.accession_number})",
        "",
    ]
    return "\n".join(lines)


def _news_block(item: "NewsItem", sector_tickers: set[str]) -> str:
    marker = NEWS_SENTIMENT_MARKERS.get(item.overall_sentiment_label, "•")
    mentioned = ", ".join(t for t in item.tickers if t in sector_tickers) or "sector-wide"
    lines = [
        f"- {marker} **[{item.title}]({item.url})**  ",
        f"  {item.source} · {item.published.strftime('%Y-%m-%d %H:%M')} UTC · "
        f"tickers: {mentioned} · sentiment: {item.overall_sentiment_label}",
    ]
    if item.summary:
        lines.append(f"  {item.summary}")
    return "\n".join(lines)


def render_memo(result: "PipelineResult") -> str:
    sector = result.sector
    events = result.events
    highlights = [e for e in events if e.materiality >= HIGHLIGHT_THRESHOLD]
    silent_count = len(sector.tickers) - len(result.companies_with_events)

    lines: list[str] = []

    if result.mode == "offline":
        lines += [
            "> **SAMPLE DATA -- not real SEC filings.** This memo was "
            "generated in `offline` mode from `secmonitor/fixtures.py`, a "
            "hand-written synthetic week used for development, testing, "
            "and demonstration. Company tickers/names are real; the events "
            "attributed to them are invented. Run with `--mode live` "
            "(requires network access to sec.gov and a contact email) for "
            "real EDGAR data.",
            "",
        ]

    lines += [
        f"# {sector.name} -- Weekly 8-K Monitor",
        "",
        f"**Coverage window:** {result.week_start.isoformat()} to "
        f"{result.week_end.isoformat()}  ",
        f"**Universe:** {len(sector.tickers)} companies  ",
        f"**Filings captured:** {len(events)} across "
        f"{len(result.companies_with_events)} companies "
        f"({silent_count} had no reportable 8-K this week)  ",
        "**Data source:** SEC EDGAR (facts only -- commentary below is "
        "rule-based analyst scaffolding, not investment advice)",
        "",
        "---",
        "",
    ]

    if highlights:
        lines.append(f"## Highlights (materiality >= {HIGHLIGHT_THRESHOLD})")
        lines.append("")
        for event in highlights:
            lines.append(_event_block(event, heading_level=3))
        lines.append("---")
        lines.append("")

    lines.append("## All events this week, by category")
    lines.append("")
    by_category: dict[str, list["ScoredEvent"]] = {}
    for event in events:
        by_category.setdefault(event.primary_category.code, []).append(event)

    for code in sorted(by_category, key=lambda c: -by_category[c][0].primary_category.base_materiality):
        cat_events = by_category[code]
        label = cat_events[0].primary_category.label
        lines.append(f"### {label} ({len(cat_events)})")
        lines.append("")
        for event in cat_events:
            lines.append(_event_block(event, heading_level=4))
        lines.append("")

    if not events:
        lines.append("_No 8-K filings matched the coverage window for this universe._")
        lines.append("")

    if result.news or result.news_warnings:
        lines.append("---")
        lines.append("")
        lines.append("## This week in sector news")
        lines.append("")
        lines.append(
            "**Data source:** Alpha Vantage NEWS_SENTIMENT -- a real, independent "
            "news feed. This section is *not* derived from EDGAR and isn't matched "
            "to the filings above; it's supplementary market context for the same "
            "coverage window."
        )
        lines.append("")
        if result.news:
            sector_tickers = set(sector.tickers)
            for item in result.news:
                lines.append(_news_block(item, sector_tickers))
                lines.append("")
        else:
            lines.append("_No news items were returned for this window._")
            lines.append("")
        if result.news_warnings:
            lines.append(f"_{len(result.news_warnings)} news batch(es) failed -- see logs._")
            lines.append("")

    lines += [
        "---",
        "",
        "## Methodology",
        "",
        "**Classification.** Each 8-K's disclosed Item codes (e.g. `5.02` = "
        "officer/director departure or election) map directly to an event "
        "category -- see `secmonitor/events.py`. A filing with multiple "
        "items is headlined by its most material substantive item.",
        "",
        "**Scoring.** Materiality and urgency (1-10 each) start from a "
        "per-category baseline and are adjusted by a small set of "
        "documented keyword rules (e.g. \"material weakness\" on a "
        "restatement filing, \"CEO\"/\"CFO\" on a leadership-change filing) "
        "-- see `secmonitor/scoring.py`. Every score in this memo carries "
        "its rationale so it can be checked, not just trusted.",
        "",
        "**Known limitations.** Keyword matching is blunt -- it doesn't "
        "understand negation, deal size in dollars, or company-specific "
        "context, and the \"Other Material Events\" catch-all (Item 8.01) "
        "spans everything from routine press releases to major litigation "
        "with the same base score. \"Why it matters\" / \"Watch next\" text "
        "is templated per category, not a per-company financial analysis. "
        "Treat every score as a triage signal -- read the linked filing "
        "before acting on it.",
        "",
    ]

    return "\n".join(lines)
