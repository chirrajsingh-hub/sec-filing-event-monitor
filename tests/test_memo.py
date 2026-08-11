from datetime import date

from secmonitor.memo import render_weekly_memo
from secmonitor.models import Company, EventTag, Filing, FilingEvent, MaterialityScore


def _make_event(ticker: str, category: str, weight: int, level: str) -> FilingEvent:
    company = Company(ticker=ticker, name=f"{ticker} Corp", sector="Semiconductors", cik="0000000001")
    filing = Filing(
        company=company,
        accession_number=f"0000000001-26-{weight:06d}",
        filing_date=date(2026, 8, 5),
        form="8-K",
        items=["5.02"],
        primary_document="form8k.htm",
        filing_index_url="https://www.sec.gov/Archives/edgar/data/1/000000000126000001-index.htm",
        document_url="https://www.sec.gov/Archives/edgar/data/1/000000000126000001/form8k.htm",
    )
    tag = EventTag(code="5.02", label="Departure/Election of Directors or Officers", category=category, weight=weight)
    materiality = MaterialityScore(score=weight, level=level, rationale="test rationale")
    return FilingEvent(
        filing=filing,
        tags=[tag],
        materiality=materiality,
        what_happened="Something happened.",
        why_it_matters="It matters because of reasons.",
        thesis_impact="Check the thesis.",
        source="template",
    )


def test_render_weekly_memo_empty():
    memo = render_weekly_memo([], date(2026, 8, 1), date(2026, 8, 8))
    assert "No material 8-K filings" in memo


def test_render_weekly_memo_groups_by_materiality_tier():
    events = [
        _make_event("AAA", "leadership_change", 5, "Critical"),
        _make_event("BBB", "earnings", 2, "Low"),
    ]
    memo = render_weekly_memo(events, date(2026, 8, 1), date(2026, 8, 8), sector="Semiconductors")

    assert "# Weekly SEC 8-K Monitor — Semiconductors Sector" in memo
    assert "## Critical Materiality" in memo
    assert "## Low Materiality" in memo
    critical_idx = memo.index("## Critical Materiality")
    low_idx = memo.index("## Low Materiality")
    assert critical_idx < low_idx
    assert "AAA Corp (AAA)" in memo
    assert "[SEC EDGAR filing](https://www.sec.gov" in memo


def test_render_weekly_memo_flags_template_source():
    events = [_make_event("AAA", "leadership_change", 3, "Medium")]
    memo = render_weekly_memo(events, date(2026, 8, 1), date(2026, 8, 8))
    assert "template-generated" in memo
