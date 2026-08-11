"""Orchestrates the end-to-end run: resolve tickers -> fetch 8-Ks -> classify
-> score -> summarize -> persist. This is the one place that ties the other
modules together; each of them stays independently testable."""

from __future__ import annotations

from datetime import date
from typing import List, Optional

from secmonitor.config import Settings, load_companies
from secmonitor.edgar import EdgarClient
from secmonitor.events import classify_items, refine_catchall_category
from secmonitor.models import Company, Filing, FilingEvent
from secmonitor.scoring import score_filing
from secmonitor.storage import EventStore
from secmonitor.summarizer import generate_narrative


def build_event(filing: Filing, settings: Settings, client: EdgarClient) -> FilingEvent:
    tags = classify_items(filing.items)

    excerpt = None
    if settings.fetch_document_text:
        excerpt = client.fetch_document_text(filing, max_chars=settings.max_document_chars)
        tags = refine_catchall_category(tags, excerpt or "")

    materiality = score_filing(tags, excerpt)
    what, why, thesis, source = generate_narrative(
        filing, tags, excerpt, api_key=settings.anthropic_api_key
    )

    return FilingEvent(
        filing=filing,
        tags=tags,
        materiality=materiality,
        what_happened=what,
        why_it_matters=why,
        thesis_impact=thesis,
        excerpt=excerpt,
        source=source,
    )


def run_pipeline(
    settings: Settings,
    since: date,
    until: date,
    companies: Optional[List[Company]] = None,
    store: Optional[EventStore] = None,
    skip_seen: bool = True,
) -> List[FilingEvent]:
    companies = companies if companies is not None else load_companies()
    client = EdgarClient(
        user_agent=settings.user_agent,
        request_delay_seconds=settings.request_delay_seconds,
        cache_dir=settings.data_dir / "cache",
    )
    store = store or EventStore(settings.data_dir / "secmonitor.db")

    resolved = client.resolve_companies(companies)

    events: List[FilingEvent] = []
    for company in resolved:
        for filing in client.iter_recent_8k(company, since, until):
            if skip_seen and store.has_seen(filing.accession_number):
                continue
            event = build_event(filing, settings, client)
            store.save(event)
            events.append(event)

    events.sort(key=lambda e: (e.materiality.score, e.filing.filing_date), reverse=True)
    return events
