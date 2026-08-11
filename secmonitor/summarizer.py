"""Turns a classified filing into the three narrative fields of the memo:
what happened, why it matters, and the valuation/risk/thesis angle.

Two modes:
  - Template mode (default, no API key needed): deterministic, category-aware
    boilerplate. Runs offline, is free, and is good enough to produce a
    structurally complete memo.
  - LLM mode (set ANTHROPIC_API_KEY): asks Claude to ground the same three
    fields in the actual filing excerpt, which reads far more like real
    analyst commentary. Falls back to template mode on any error so the
    pipeline never breaks because of a flaky API call.
"""

from __future__ import annotations

import json
import os
from typing import List, Optional, Tuple

from secmonitor.models import EventTag, Filing

CATEGORY_TEMPLATES = {
    "earnings": dict(
        what="{company} ({ticker}) filed an 8-K disclosing results of operations and financial condition.",
        why="Earnings filings reset the market's read on the operating trend; the key questions are whether "
            "revenue/margin came in above or below prior guidance and whether forward guidance moved.",
        thesis="Re-run the model off the reported and guided numbers before the print's move fades; flag if "
               "consensus estimates need revision.",
    ),
    "m_and_a": dict(
        what="{company} ({ticker}) disclosed an acquisition, disposition, or completion of a material asset transaction.",
        why="M&A changes the asset base, competitive positioning, and often the balance sheet (cash, debt, or "
            "share count) all at once.",
        thesis="Check deal terms (cash vs. stock, multiple paid/received, financing source) against the "
               "standalone thesis; M&A is a common source of both value creation and value destruction.",
    ),
    "leadership_change": dict(
        what="{company} ({ticker}) disclosed the departure or election of a director or executive officer.",
        why="Leadership turnover, especially in the CEO/CFO/CAO seats or an abrupt/unexplained departure, is "
            "a leading indicator watched closely for governance or performance issues.",
        thesis="Note whether the departure was announced as a planned succession or was abrupt/for cause; the "
               "latter warrants a closer look at recent internal controls or strategy disputes.",
    ),
    "debt_financing": dict(
        what="{company} ({ticker}) disclosed a new direct financial obligation or a triggering event affecting existing debt.",
        why="New debt changes leverage and interest expense; a triggering/acceleration event signals covenant "
            "or liquidity stress.",
        thesis="Update the leverage and interest-coverage assumptions in the model; treat acceleration clauses "
               "as a liquidity-risk flag worth monitoring closely.",
    ),
    "restatement": dict(
        what="{company} ({ticker}) disclosed non-reliance on previously issued financial statements.",
        why="A restatement is one of the highest-severity disclosures in the 8-K taxonomy: it means prior "
            "reported financials can no longer be trusted as filed.",
        thesis="Treat as a critical risk flag. Re-verify any thesis inputs sourced from the periods under "
              "restatement and watch for follow-on auditor, litigation, or delisting risk.",
    ),
    "cyber": dict(
        what="{company} ({ticker}) disclosed a material cybersecurity incident.",
        why="Item 1.05 cyber disclosures are new (2023 rule) and reserved for incidents the company has "
            "determined to be material, so the bar for filing is itself a signal.",
        thesis="Assess exposure: data/IP loss, operational downtime, remediation cost, and potential "
               "regulatory or customer-contract fallout.",
    ),
    "bankruptcy": dict(
        what="{company} ({ticker}) disclosed a bankruptcy or receivership filing.",
        why="This is typically a going-concern-level event with equity holders often subordinated to "
            "creditors in any recovery.",
        thesis="Re-underwrite from a distressed/recovery framework rather than a going-concern equity thesis.",
    ),
    "delisting": dict(
        what="{company} ({ticker}) disclosed a delisting notice or failure to satisfy a listing standard.",
        why="Delisting risk affects liquidity, index eligibility, and can trigger further capital-raising or "
            "governance stress.",
        thesis="Check which listing standard is at issue (price, market cap, filing timeliness) and the "
               "cure period before it becomes a forced-seller event.",
    ),
    "control_change": dict(
        what="{company} ({ticker}) disclosed a change in control of the registrant.",
        why="A change-of-control event can shift strategy, capital allocation, and existing shareholder "
            "agreements overnight.",
        thesis="Identify the acquiring party/new controlling holder and any resulting related-party dynamics.",
    ),
    "impairment": dict(
        what="{company} ({ticker}) disclosed a material impairment.",
        why="Impairments are a non-cash but informative admission that previously capitalized value "
            "(goodwill, intangibles, PP&E) is no longer supportable.",
        thesis="Check which asset/segment was written down; it often confirms a thesis-relevant deterioration "
               "the market has already been pricing in via multiple compression.",
    ),
    "restructuring": dict(
        what="{company} ({ticker}) disclosed exit or disposal activity costs.",
        why="Restructuring charges signal a strategic reset -- cost-cutting, footprint reduction, or exiting "
            "a line of business.",
        thesis="Separate one-time charges from any read-through to the ongoing margin structure.",
    ),
    "accountant_change": dict(
        what="{company} ({ticker}) disclosed a change in its certifying accountant.",
        why="Auditor changes outside a routine rotation cycle are watched as a potential precursor to "
            "accounting or disclosure disputes.",
        thesis="Read the reason for dismissal/resignation in the filing closely; disagreements over "
               "accounting treatment are a red flag worth flagging explicitly.",
    ),
    "equity_issuance": dict(
        what="{company} ({ticker}) disclosed an unregistered sale of equity securities.",
        why="New equity issuance is dilutive and can also signal a liquidity need or a financing for a "
            "specific strategic use of proceeds.",
        thesis="Model the dilution and compare the issuance price/terms to where the stock is trading.",
    ),
    "litigation": dict(
        what="{company} ({ticker}) disclosed litigation, investigation, or regulatory inquiry developments.",
        why="Litigation exposure carries both a direct financial-liability tail and a reputational/customer "
            "relationship risk.",
        thesis="Size the potential liability against the balance sheet and flag whether it's accrued for "
               "or disclosed only as a contingency.",
    ),
    "going_concern": dict(
        what="{company} ({ticker}) disclosed language raising substantial doubt about its ability to continue "
             "as a going concern.",
        why="This is among the most severe disclosures a filer can make and is closely tied to near-term "
            "liquidity and financing risk.",
        thesis="Treat as a critical risk flag; verify liquidity runway and any covenant or refinancing "
               "deadlines referenced in the filing.",
    ),
    "material_agreement": dict(
        what="{company} ({ticker}) disclosed entry into or termination of a material definitive agreement.",
        why="Material agreements (supply, customer, partnership, credit) can move forward revenue or cost "
            "assumptions meaningfully depending on size and term.",
        thesis="Check counterparty, contract value/duration if disclosed, and whether it's incremental to "
               "or a renewal of existing business.",
    ),
    "governance": dict(
        what="{company} ({ticker}) disclosed a governance-related item (bylaw amendment, shareholder vote, "
             "or code-of-ethics matter).",
        why="Governance filings are usually procedural but occasionally telegraph a broader strategic or "
            "activist-driven change.",
        thesis="Usually low-impact; skim for any tie-in to a broader campaign (e.g., activist investor, "
               "proxy fight) before dismissing.",
    ),
    "disclosure": dict(
        what="{company} ({ticker}) made a Regulation FD disclosure.",
        why="Reg FD filings are how companies broadly disclose information also shared selectively, often "
            "investor-presentation or conference material.",
        thesis="Check the attached exhibit for any updated guidance, KPIs, or strategic commentary.",
    ),
    "other_material_event": dict(
        what="{company} ({ticker}) disclosed an Item 8.01 'Other Events' filing.",
        why="Item 8.01 is a catch-all; the filing text itself (not the item code) determines whether this "
            "is market-moving or routine.",
        thesis="Read the attached press release/exhibit directly -- this bucket ranges from routine "
               "announcements to major unscheduled news.",
    ),
    "exhibits_only": dict(
        what="{company} ({ticker}) filed exhibits only (Item 9.01), typically accompanying another item on "
             "the same or a related filing.",
        why="Rarely material on its own; usually supporting documentation for a substantive item elsewhere "
            "in the same filing.",
        thesis="Low priority unless paired with a high-materiality item in the same accession.",
    ),
    "other": dict(
        what="{company} ({ticker}) filed an 8-K with an item code outside the standard taxonomy.",
        why="Uncommon item codes are worth a manual look since they fall outside routine categories.",
        thesis="Read the source filing directly before drawing a conclusion.",
    ),
}


def _template_narrative(filing: Filing, tags: List[EventTag]) -> Tuple[str, str, str]:
    primary = max(tags, key=lambda t: t.weight) if tags else None
    category = primary.category if primary else "other"
    tmpl = CATEGORY_TEMPLATES.get(category, CATEGORY_TEMPLATES["other"])
    fmt = dict(company=filing.company.name, ticker=filing.company.ticker)
    return (
        tmpl["what"].format(**fmt),
        tmpl["why"].format(**fmt),
        tmpl["thesis"].format(**fmt),
    )


LLM_SYSTEM_PROMPT = (
    "You are an equity research associate writing terse, factual notes on SEC 8-K filings for a "
    "weekly sector monitor. Given a filing's metadata and an excerpt of its text, respond with ONLY "
    "a JSON object with exactly these keys: \"what_happened\" (1 sentence, factual), "
    "\"why_it_matters\" (1-2 sentences on why this is relevant to investors), and \"thesis_impact\" "
    "(1-2 sentences on the valuation/risk/thesis angle an analyst should check next). Do not "
    "speculate beyond what the excerpt supports. No markdown, no preamble, JSON only."
)


def _llm_narrative(filing: Filing, tags: List[EventTag], excerpt: Optional[str],
                    api_key: str, model: str) -> Optional[Tuple[str, str, str]]:
    try:
        import anthropic
    except ImportError:
        return None

    item_summary = ", ".join(f"{t.code} ({t.label})" for t in tags) or "none"
    user_content = (
        f"Company: {filing.company.name} ({filing.company.ticker})\n"
        f"Filing date: {filing.filing_date.isoformat()}\n"
        f"Form: {filing.form}\n"
        f"Items: {item_summary}\n"
        f"Excerpt: {(excerpt or '')[:4000]}\n"
    )
    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=400,
            system=LLM_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        raw_text = "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
        parsed = json.loads(raw_text)
        return (parsed["what_happened"], parsed["why_it_matters"], parsed["thesis_impact"])
    except Exception:
        return None


def generate_narrative(
    filing: Filing,
    tags: List[EventTag],
    excerpt: Optional[str] = None,
    api_key: Optional[str] = None,
    model: str = "claude-sonnet-5",
) -> Tuple[str, str, str, str]:
    """Returns (what_happened, why_it_matters, thesis_impact, source)."""
    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        result = _llm_narrative(filing, tags, excerpt, api_key, model)
        if result is not None:
            return (*result, "llm")

    what, why, thesis = _template_narrative(filing, tags)
    return (what, why, thesis, "template")
