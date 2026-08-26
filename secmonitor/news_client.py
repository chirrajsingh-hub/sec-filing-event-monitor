"""Optional real-news enrichment via Alpha Vantage's NEWS_SENTIMENT endpoint.

This is deliberately a *second, independent* data source, not a
replacement for EDGAR: Alpha Vantage has no notion of an 8-K or an Item
code, so it can't classify or score filings the way `edgar_client` does.
What it does have is a real news feed -- articles from financial outlets,
tagged per-ticker with a relevance score and a sentiment label -- which is
useful context to run alongside the filings, not instead of them. The memo
renders it as its own "This Week in Sector News" section (see `memo.py`)
rather than trying to fuzzily attach articles to specific filings, since
that kind of date/topic matching would be more guesswork than signal.

Get a free key at https://www.alphavantage.co/support/#api-key. The free
tier is rate- and quota-limited (historically 5 requests/minute and 25
requests/day -- check Alpha Vantage's site for the current numbers, they
change it periodically), which is why this client fetches the whole
tracked universe in a small number of batched calls (comma-separated
tickers in one request) rather than one call per company.

Like `edgar_client`, the HTTP call is isolated in one function so the
parsing logic is unit-testable against a hand-built JSON fixture without
a live connection or a real API key -- see `tests/test_sec_news_client.py`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime

import requests

API_URL = "https://www.alphavantage.co/query"

# Alpha Vantage's free tier has historically allowed 5 requests/minute.
# This stays comfortably under that regardless of what the current limit
# is; it does NOT track the separate daily quota, which callers should
# manage themselves by keeping TICKER_BATCH_SIZE and the number of batches
# small (see `AlphaVantageClient.get_news_for_tickers`).
MIN_REQUEST_INTERVAL_SECONDS = 13.0
TICKER_BATCH_SIZE = 10


class RateLimitedError(RuntimeError):
    """Raised when Alpha Vantage responds with a quota/rate-limit notice
    instead of data (it does this with a 200 OK and a "Note"/"Information"
    field, not an HTTP error code, so it has to be checked explicitly)."""


@dataclass(frozen=True)
class TickerSentiment:
    ticker: str
    relevance_score: float
    sentiment_score: float
    sentiment_label: str


@dataclass(frozen=True)
class NewsItem:
    title: str
    url: str
    source: str
    published: datetime
    summary: str
    overall_sentiment_label: str
    overall_sentiment_score: float
    ticker_sentiments: list[TickerSentiment] = field(default_factory=list)

    @property
    def tickers(self) -> list[str]:
        return [t.ticker for t in self.ticker_sentiments]


def _parse_published(raw: str) -> datetime:
    # Alpha Vantage's format: "20260809T143000"
    return datetime.strptime(raw, "%Y%m%dT%H%M%S")


def parse_news_sentiment(payload: dict) -> list[NewsItem]:
    """Parse a NEWS_SENTIMENT response into NewsItem records.

    Raises RateLimitedError if the payload is Alpha Vantage's quota/rate
    notice rather than a real feed -- that response is a 200 with a
    `"Note"` or `"Information"` key and no `"feed"` key.
    """
    if "feed" not in payload:
        message = payload.get("Note") or payload.get("Information") or str(payload)
        raise RateLimitedError(f"Alpha Vantage did not return a feed: {message}")

    items: list[NewsItem] = []
    for entry in payload["feed"]:
        ticker_sentiments = [
            TickerSentiment(
                ticker=t["ticker"],
                relevance_score=float(t["relevance_score"]),
                sentiment_score=float(t["ticker_sentiment_score"]),
                sentiment_label=t["ticker_sentiment_label"],
            )
            for t in entry.get("ticker_sentiment", [])
        ]
        items.append(
            NewsItem(
                title=entry["title"],
                url=entry["url"],
                source=entry.get("source", ""),
                published=_parse_published(entry["time_published"]),
                summary=entry.get("summary", ""),
                overall_sentiment_label=entry.get("overall_sentiment_label", "Neutral"),
                overall_sentiment_score=float(entry.get("overall_sentiment_score", 0.0)),
                ticker_sentiments=ticker_sentiments,
            )
        )
    return items


def _get_json(url: str, params: dict) -> dict:
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def _batched(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


class AlphaVantageClient:
    """Thin, rate-limited wrapper around Alpha Vantage's NEWS_SENTIMENT endpoint."""

    def __init__(self, api_key: str, min_interval: float = MIN_REQUEST_INTERVAL_SECONDS):
        if not api_key:
            raise ValueError(
                "AlphaVantageClient requires an api_key -- get a free one at "
                "https://www.alphavantage.co/support/#api-key"
            )
        self.api_key = api_key
        self.min_interval = min_interval
        self._last_request_at = 0.0

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last_request_at = time.monotonic()

    def get_news_sentiment(
        self,
        tickers: list[str],
        limit: int = 50,
        time_from: datetime | None = None,
        time_to: datetime | None = None,
    ) -> list[NewsItem]:
        """One NEWS_SENTIMENT call for a batch of tickers (comma-separated)."""
        self._throttle()
        params = {
            "function": "NEWS_SENTIMENT",
            "tickers": ",".join(tickers),
            "limit": limit,
            "apikey": self.api_key,
        }
        if time_from is not None:
            params["time_from"] = time_from.strftime("%Y%m%dT%H%M")
        if time_to is not None:
            params["time_to"] = time_to.strftime("%Y%m%dT%H%M")
        payload = _get_json(API_URL, params)
        return parse_news_sentiment(payload)

    def get_news_for_tickers(
        self,
        tickers: list[str],
        limit_per_batch: int = 50,
        time_from: datetime | None = None,
        time_to: datetime | None = None,
    ) -> tuple[list[NewsItem], list[str]]:
        """Fetch news for a full ticker universe in size-limited batches.

        Returns (news_items, warnings) -- a single batch's rate-limit/HTTP
        failure is recorded as a warning and skipped rather than aborting
        the whole run, same as `edgar_client`'s per-company error handling.
        """
        all_items: list[NewsItem] = []
        warnings: list[str] = []
        for batch in _batched(tickers, TICKER_BATCH_SIZE):
            try:
                all_items.extend(
                    self.get_news_sentiment(
                        batch, limit=limit_per_batch, time_from=time_from, time_to=time_to
                    )
                )
            except Exception as exc:  # noqa: BLE001 -- one bad batch shouldn't kill the run
                warnings.append(f"news batch {batch}: {exc}")
        # De-dupe articles that mention tickers from more than one batch.
        seen: set[str] = set()
        deduped = []
        for item in all_items:
            if item.url in seen:
                continue
            seen.add(item.url)
            deduped.append(item)
        deduped.sort(key=lambda i: i.published, reverse=True)
        return deduped, warnings
