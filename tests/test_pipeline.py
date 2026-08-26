from datetime import date

import pytest

from secmonitor.pipeline import MODE_LIVE, MODE_OFFLINE, run_pipeline
from secmonitor.universe import SEMICONDUCTORS


def test_offline_pipeline_returns_events_sorted_by_combined_score():
    result = run_pipeline(mode=MODE_OFFLINE, weeks_back=1, as_of=date(2026, 8, 11))
    assert result.mode == MODE_OFFLINE
    assert len(result.events) > 0

    scores = [e.combined_score for e in result.events]
    assert scores == sorted(scores, reverse=True)


def test_offline_pipeline_only_includes_events_within_the_universe():
    result = run_pipeline(mode=MODE_OFFLINE, weeks_back=1, as_of=date(2026, 8, 11))
    tickers = {c.ticker for c in SEMICONDUCTORS.companies}
    assert all(e.ticker in tickers for e in result.events)


def test_offline_pipeline_respects_weeks_back_window():
    as_of = date(2026, 8, 11)
    wide = run_pipeline(mode=MODE_OFFLINE, weeks_back=2, as_of=as_of)
    narrow = run_pipeline(mode=MODE_OFFLINE, weeks_back=0, as_of=as_of)
    assert len(narrow.events) <= len(wide.events)
    assert all(e.filing_date >= narrow.week_start for e in narrow.events)


def test_offline_pipeline_produces_renderable_memo():
    result = run_pipeline(mode=MODE_OFFLINE, as_of=date(2026, 8, 11))
    memo = result.render_memo()
    assert "Weekly 8-K Monitor" in memo
    assert "SAMPLE DATA" in memo


def test_offline_pipeline_dataframe_has_expected_columns():
    result = run_pipeline(mode=MODE_OFFLINE, as_of=date(2026, 8, 11))
    df = result.to_dataframe()
    assert set(df.columns) >= {
        "ticker", "company", "filing_date", "category",
        "materiality", "urgency", "combined_score", "edgar_url",
    }
    assert len(df) == len(result.events)


def test_live_mode_requires_contact_email():
    with pytest.raises(ValueError):
        run_pipeline(mode=MODE_LIVE, contact_email=None)


def test_unknown_mode_raises():
    with pytest.raises(ValueError):
        run_pipeline(mode="not-a-real-mode")


def test_live_mode_collects_failures_as_warnings_not_exceptions(monkeypatch):
    from secmonitor import pipeline as pipeline_module

    class ExplodingClient:
        def __init__(self, contact_email):
            pass

        def get_recent_8k_filings(self, ticker, company, since):
            raise RuntimeError("simulated network failure")

    monkeypatch.setattr(pipeline_module, "EdgarClient", ExplodingClient)

    result = run_pipeline(mode=MODE_LIVE, contact_email="test@example.com")
    assert result.events == []
    assert len(result.warnings) == len(SEMICONDUCTORS.companies)


def test_news_is_skipped_without_an_alpha_vantage_key():
    result = run_pipeline(mode=MODE_OFFLINE, as_of=date(2026, 8, 11))
    assert result.news == []
    assert result.news_warnings == []
    assert "sector news" not in result.render_memo()


def test_news_is_fetched_when_alpha_vantage_key_provided(monkeypatch):
    from secmonitor import pipeline as pipeline_module
    from secmonitor.news_client import NewsItem
    from datetime import datetime

    sample_item = NewsItem(
        title="Sample sector news", url="https://example.com/a", source="Wire",
        published=datetime(2026, 8, 9), summary="Something happened.",
        overall_sentiment_label="Neutral", overall_sentiment_score=0.0,
    )

    class FakeAlphaVantageClient:
        def __init__(self, api_key):
            assert api_key == "testkey"

        def get_news_for_tickers(self, tickers, time_from=None, time_to=None):
            return [sample_item], []

    monkeypatch.setattr(pipeline_module, "AlphaVantageClient", FakeAlphaVantageClient)

    result = run_pipeline(mode=MODE_OFFLINE, as_of=date(2026, 8, 11), alpha_vantage_key="testkey")
    assert result.news == [sample_item]
    memo = result.render_memo()
    assert "sector news" in memo.lower()
    assert "Sample sector news" in memo


def test_news_batch_failures_surface_as_warnings_not_exceptions(monkeypatch):
    from secmonitor import pipeline as pipeline_module

    class FailingAlphaVantageClient:
        def __init__(self, api_key):
            pass

        def get_news_for_tickers(self, tickers, time_from=None, time_to=None):
            return [], ["news batch ['AMD']: boom"]

    monkeypatch.setattr(pipeline_module, "AlphaVantageClient", FailingAlphaVantageClient)

    result = run_pipeline(mode=MODE_OFFLINE, as_of=date(2026, 8, 11), alpha_vantage_key="testkey")
    assert result.news == []
    assert result.news_warnings == ["news batch ['AMD']: boom"]
