"""Orchestration: pull filings, classify, score, and render the weekly memo.

Two modes:

  offline (default) -- reads `secmonitor.fixtures.sample_filings`, a
      hand-written, clearly-labeled synthetic week. Needs no network
      access and no SEC contact email; this is what the test suite and
      the bundled example script run by default.

  live -- pulls real 8-Ks from EDGAR via `secmonitor.edgar_client`. Needs
      outbound network access to sec.gov/data.sec.gov (not available in
      every sandboxed environment -- this one included, see the project
      README) and a real contact email for the required SEC User-Agent
      header.

Per-company failures in live mode (a delisted ticker, a transient HTTP
error) are caught and reported rather than aborting the whole run --
a monitor covering 30 companies shouldn't go dark because one ticker's
lookup failed.

A third, optional data source layers on top of either mode: pass
`alpha_vantage_key` (or set ALPHAVANTAGE_API_KEY) to add a real news feed
via `secmonitor.news_client`, rendered as its own memo section independent
of the EDGAR events -- see that module's docstring for why it isn't fused
into the filings themselves.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import pandas as pd

from secmonitor import fixtures
from secmonitor.edgar_client import EdgarClient, FilingRecord
from secmonitor.events import EventCategory, item_categories, primary_category
from secmonitor.memo import render_memo
from secmonitor.news_client import AlphaVantageClient, NewsItem
from secmonitor.scoring import Score, score_filing
from secmonitor.universe import DEFAULT_SECTOR, Sector

MODE_OFFLINE = "offline"
MODE_LIVE = "live"


@dataclass(frozen=True)
class ScoredEvent:
    ticker: str
    company: str
    filing_date: date
    items: list[str]
    primary_category: EventCategory
    categories: list[EventCategory]
    headline: str
    snippet: str
    accession_number: str
    edgar_url: str
    index_url: str
    materiality: int
    urgency: int
    rationale: list[str]

    @property
    def combined_score(self) -> int:
        return self.materiality + self.urgency

    @property
    def rationale_joined(self) -> str:
        return "; ".join(self.rationale)


@dataclass
class PipelineResult:
    sector: Sector
    mode: str
    week_start: date
    week_end: date
    events: list[ScoredEvent]
    warnings: list[str] = field(default_factory=list)
    news: list[NewsItem] = field(default_factory=list)
    news_warnings: list[str] = field(default_factory=list)

    @property
    def companies_with_events(self) -> set[str]:
        return {e.ticker for e in self.events}

    def to_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "ticker": e.ticker,
                    "company": e.company,
                    "filing_date": e.filing_date,
                    "items": ",".join(e.items),
                    "category": e.primary_category.label,
                    "materiality": e.materiality,
                    "urgency": e.urgency,
                    "combined_score": e.combined_score,
                    "headline": e.headline,
                    "edgar_url": e.edgar_url,
                    "rationale": e.rationale_joined,
                }
                for e in self.events
            ]
        )

    def render_memo(self) -> str:
        return render_memo(self)


def _build_scored_event(record: FilingRecord, headline: str, snippet: str) -> ScoredEvent:
    categories = item_categories(record.items)
    primary = primary_category(record.items)
    headline = headline.strip() or (
        f"{record.company} ({record.ticker}) files Item {primary.code} -- {primary.label}"
    )
    score: Score = score_filing(record.items, headline, snippet)
    return ScoredEvent(
        ticker=record.ticker,
        company=record.company,
        filing_date=record.filing_date,
        items=record.items,
        primary_category=primary,
        categories=categories,
        headline=headline,
        snippet=snippet.strip(),
        accession_number=record.accession_number,
        edgar_url=record.edgar_url,
        index_url=record.index_url,
        materiality=score.materiality,
        urgency=score.urgency,
        rationale=score.rationale,
    )


def _collect_offline(sector: Sector, week_start: date, as_of: date) -> list[ScoredEvent]:
    tickers = set(sector.tickers)
    events = []
    for record, headline, snippet in fixtures.sample_filings(as_of=as_of):
        if record.ticker not in tickers:
            continue
        if record.filing_date < week_start:
            continue
        events.append(_build_scored_event(record, headline, snippet))
    return events


def _collect_live(
    sector: Sector, week_start: date, contact_email: str, warnings: list[str]
) -> list[ScoredEvent]:
    client = EdgarClient(contact_email=contact_email)
    events = []
    for company in sector.companies:
        try:
            records = client.get_recent_8k_filings(company.ticker, company.name, since=week_start)
        except Exception as exc:  # noqa: BLE001 -- one bad ticker shouldn't kill the run
            warnings.append(f"{company.ticker}: failed to fetch filings ({exc})")
            continue
        for record in records:
            # Live mode has no cheap source of filing-text snippets yet
            # (see README limitations) -- scoring falls back to the
            # item-code baseline plus a generated headline.
            events.append(_build_scored_event(record, headline="", snippet=""))
    return events


def _collect_news(
    sector: Sector, week_start: date, as_of: date, alpha_vantage_key: str
) -> tuple[list[NewsItem], list[str]]:
    client = AlphaVantageClient(api_key=alpha_vantage_key)
    return client.get_news_for_tickers(
        sector.tickers,
        time_from=datetime.combine(week_start, datetime.min.time()),
        time_to=datetime.combine(as_of, datetime.max.time().replace(microsecond=0)),
    )


def run_pipeline(
    sector: Sector = DEFAULT_SECTOR,
    mode: str = MODE_OFFLINE,
    weeks_back: int = 1,
    contact_email: str | None = None,
    alpha_vantage_key: str | None = None,
    as_of: date | None = None,
) -> PipelineResult:
    as_of = as_of or date.today()
    week_start = as_of - timedelta(weeks=weeks_back)
    warnings: list[str] = []

    if mode == MODE_OFFLINE:
        events = _collect_offline(sector, week_start, as_of)
    elif mode == MODE_LIVE:
        if not contact_email:
            raise ValueError("mode='live' requires contact_email for the SEC User-Agent header")
        events = _collect_live(sector, week_start, contact_email, warnings)
    else:
        raise ValueError(f"Unknown mode {mode!r}; expected {MODE_OFFLINE!r} or {MODE_LIVE!r}")

    events.sort(key=lambda e: (e.combined_score, e.materiality), reverse=True)

    # News is an independent, optional real-data layer -- see news_client.py.
    # It's fetched regardless of `mode` (offline EDGAR fixtures + real news
    # is a legitimate combination while developing without EDGAR access).
    news: list[NewsItem] = []
    news_warnings: list[str] = []
    if alpha_vantage_key:
        news, news_warnings = _collect_news(sector, week_start, as_of, alpha_vantage_key)

    for w in warnings + news_warnings:
        print(f"warning: {w}", file=sys.stderr)

    return PipelineResult(
        sector=sector, mode=mode, week_start=week_start, week_end=as_of,
        events=events, warnings=warnings, news=news, news_warnings=news_warnings,
    )
