from datetime import datetime

import pytest

from secmonitor import news_client
from secmonitor.news_client import (
    AlphaVantageClient,
    RateLimitedError,
    TICKER_BATCH_SIZE,
    parse_news_sentiment,
)


def _make_feed_payload():
    # Shaped like a real Alpha Vantage NEWS_SENTIMENT response.
    return {
        "items": "1",
        "sentiment_score_definition": "x",
        "relevance_score_definition": "y",
        "feed": [
            {
                "title": "AMD shares rise on AI chip demand",
                "url": "https://example.com/amd-news",
                "time_published": "20260809T143000",
                "summary": "AMD reported strong demand for its AI accelerators.",
                "source": "Example Wire",
                "overall_sentiment_score": 0.35,
                "overall_sentiment_label": "Somewhat-Bullish",
                "ticker_sentiment": [
                    {
                        "ticker": "AMD",
                        "relevance_score": "0.9",
                        "ticker_sentiment_score": "0.4",
                        "ticker_sentiment_label": "Bullish",
                    }
                ],
            }
        ],
    }


def _make_rate_limit_payload():
    return {
        "Note": "Thank you for using Alpha Vantage! Our standard API rate "
                "limit is 25 requests per day."
    }


def test_parse_news_sentiment_extracts_fields():
    items = parse_news_sentiment(_make_feed_payload())
    assert len(items) == 1
    item = items[0]
    assert item.title == "AMD shares rise on AI chip demand"
    assert item.source == "Example Wire"
    assert item.published == datetime(2026, 8, 9, 14, 30, 0)
    assert item.overall_sentiment_label == "Somewhat-Bullish"
    assert item.tickers == ["AMD"]
    assert item.ticker_sentiments[0].relevance_score == pytest.approx(0.9)
    assert item.ticker_sentiments[0].sentiment_score == pytest.approx(0.4)


def test_parse_news_sentiment_raises_on_rate_limit_note():
    with pytest.raises(RateLimitedError):
        parse_news_sentiment(_make_rate_limit_payload())


def test_parse_news_sentiment_raises_on_information_key():
    with pytest.raises(RateLimitedError):
        parse_news_sentiment({"Information": "Invalid API key."})


def test_alpha_vantage_client_requires_api_key():
    with pytest.raises(ValueError):
        AlphaVantageClient(api_key="")


def test_get_news_sentiment_calls_api_with_expected_params(monkeypatch):
    captured = {}

    def fake_get_json(url, params):
        captured["url"] = url
        captured["params"] = params
        return _make_feed_payload()

    monkeypatch.setattr(news_client, "_get_json", fake_get_json)
    client = AlphaVantageClient(api_key="testkey", min_interval=0.0)

    items = client.get_news_sentiment(["AMD", "NVDA"], limit=10)

    assert len(items) == 1
    assert captured["params"]["tickers"] == "AMD,NVDA"
    assert captured["params"]["apikey"] == "testkey"
    assert captured["params"]["function"] == "NEWS_SENTIMENT"
    assert captured["params"]["limit"] == 10


def test_get_news_for_tickers_batches_and_dedupes(monkeypatch):
    calls = []

    def fake_get_json(url, params):
        calls.append(params["tickers"])
        return _make_feed_payload()  # same article "returned" by every batch

    monkeypatch.setattr(news_client, "_get_json", fake_get_json)
    client = AlphaVantageClient(api_key="testkey", min_interval=0.0)

    tickers = [f"T{i}" for i in range(25)]  # forces multiple batches
    items, warnings = client.get_news_for_tickers(tickers)

    expected_batches = -(-len(tickers) // TICKER_BATCH_SIZE)  # ceil division
    assert len(calls) == expected_batches
    assert warnings == []
    assert len(items) == 1  # de-duplicated by URL across batches


def test_get_news_for_tickers_records_batch_failure_as_warning(monkeypatch):
    def fake_get_json(url, params):
        raise RuntimeError("boom")

    monkeypatch.setattr(news_client, "_get_json", fake_get_json)
    client = AlphaVantageClient(api_key="testkey", min_interval=0.0)

    items, warnings = client.get_news_for_tickers(["AMD"])

    assert items == []
    assert len(warnings) == 1
    assert "boom" in warnings[0]
