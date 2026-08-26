from datetime import date, datetime

from secmonitor.edgar_client import FilingRecord
from secmonitor.memo import HIGHLIGHT_THRESHOLD, render_memo
from secmonitor.news_client import NewsItem
from secmonitor.pipeline import PipelineResult, _build_scored_event
from secmonitor.universe import Company, Sector


def _sector():
    return Sector(
        name="Test Sector",
        companies=(Company("AAA", "Alpha Corp"), Company("BBB", "Beta Corp")),
    )


def _record(ticker, company, items, days_ago=1, cik="9000000001"):
    filing_date = date(2026, 8, 10) - __import__("datetime").timedelta(days=days_ago)
    return FilingRecord(
        ticker=ticker, company=company, cik=cik,
        accession_number=f"{cik}-26-000001", filing_date=filing_date,
        report_date=filing_date, items=items,
        primary_document=f"{ticker.lower()}-8k.htm",
    )


def test_render_memo_offline_mode_has_sample_data_banner():
    event = _build_scored_event(
        _record("AAA", "Alpha Corp", ["1.03"]), headline="Alpha files for bankruptcy", snippet="",
    )
    result = PipelineResult(
        sector=_sector(), mode="offline", week_start=date(2026, 8, 3),
        week_end=date(2026, 8, 10), events=[event],
    )
    memo = render_memo(result)
    assert "SAMPLE DATA" in memo


def test_render_memo_live_mode_has_no_sample_data_banner():
    event = _build_scored_event(
        _record("AAA", "Alpha Corp", ["1.03"]), headline="Alpha files for bankruptcy", snippet="",
    )
    result = PipelineResult(
        sector=_sector(), mode="live", week_start=date(2026, 8, 3),
        week_end=date(2026, 8, 10), events=[event],
    )
    memo = render_memo(result)
    assert "SAMPLE DATA" not in memo


def test_render_memo_includes_highlight_for_high_materiality_event():
    assert 9 >= HIGHLIGHT_THRESHOLD  # sanity check on the fixture below
    high = _build_scored_event(
        _record("AAA", "Alpha Corp", ["1.03"]), headline="Alpha files for bankruptcy", snippet="",
    )
    low = _build_scored_event(
        _record("BBB", "Beta Corp", ["5.07"]), headline="Beta discloses vote results", snippet="",
    )
    result = PipelineResult(
        sector=_sector(), mode="offline", week_start=date(2026, 8, 3),
        week_end=date(2026, 8, 10), events=[high, low],
    )
    memo = render_memo(result)
    assert "## Highlights" in memo
    assert "Alpha Corp (AAA)" in memo
    assert "Bankruptcy" in memo


def test_render_memo_includes_edgar_link_and_rationale():
    event = _build_scored_event(
        _record("AAA", "Alpha Corp", ["2.02"]), headline="Alpha reports earnings", snippet="",
    )
    result = PipelineResult(
        sector=_sector(), mode="offline", week_start=date(2026, 8, 3),
        week_end=date(2026, 8, 10), events=[event],
    )
    memo = render_memo(result)
    assert event.edgar_url in memo
    assert "Score rationale" in memo


def test_render_memo_reports_silent_companies():
    event = _build_scored_event(
        _record("AAA", "Alpha Corp", ["2.02"]), headline="Alpha reports earnings", snippet="",
    )
    result = PipelineResult(
        sector=_sector(), mode="offline", week_start=date(2026, 8, 3),
        week_end=date(2026, 8, 10), events=[event],
    )
    memo = render_memo(result)
    assert "1 had no reportable 8-K this week" in memo


def test_render_memo_handles_zero_events():
    result = PipelineResult(
        sector=_sector(), mode="offline", week_start=date(2026, 8, 3),
        week_end=date(2026, 8, 10), events=[],
    )
    memo = render_memo(result)
    assert "No 8-K filings matched" in memo
    assert "## Methodology" in memo


def test_render_memo_omits_news_section_when_no_key_was_used():
    result = PipelineResult(
        sector=_sector(), mode="offline", week_start=date(2026, 8, 3),
        week_end=date(2026, 8, 10), events=[],
    )
    memo = render_memo(result)
    assert "sector news" not in memo


def test_render_memo_includes_news_items_and_labels_them_as_independent():
    news_item = NewsItem(
        title="Alpha Corp announces new product line", url="https://example.com/news",
        source="Example Wire", published=datetime(2026, 8, 9, 12, 0, 0),
        summary="A short summary of the article.",
        overall_sentiment_label="Somewhat-Bullish", overall_sentiment_score=0.3,
    )
    result = PipelineResult(
        sector=_sector(), mode="offline", week_start=date(2026, 8, 3),
        week_end=date(2026, 8, 10), events=[], news=[news_item],
    )
    memo = render_memo(result)
    assert "sector news" in memo
    assert "Alpha Corp announces new product line" in memo
    assert "https://example.com/news" in memo
    assert "Alpha Vantage" in memo
    assert "not" in memo.split("sector news", 1)[1][:400]  # "not derived from EDGAR" disclaimer


def test_render_memo_reports_news_warnings():
    result = PipelineResult(
        sector=_sector(), mode="offline", week_start=date(2026, 8, 3),
        week_end=date(2026, 8, 10), events=[], news=[],
        news_warnings=["news batch ['AAA']: boom"],
    )
    memo = render_memo(result)
    assert "1 news batch" in memo
