"""SQLite-backed cache of processed filings.

Keeps the pipeline idempotent (re-running `fetch` for an overlapping date
range won't re-summarize filings it already scored) and gives the memo
generator a durable place to pull events from for an arbitrary date range,
independent of whatever the last fetch run happened to cover.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Iterator, List

from secmonitor.models import Company, EventTag, Filing, FilingEvent, MaterialityScore

SCHEMA = """
CREATE TABLE IF NOT EXISTS filing_events (
    accession_number TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    filing_date TEXT NOT NULL,
    category TEXT NOT NULL,
    materiality_score INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_filing_events_date ON filing_events(filing_date);
"""


class EventStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def has_seen(self, accession_number: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM filing_events WHERE accession_number = ?", (accession_number,)
            ).fetchone()
            return row is not None

    def save(self, event: FilingEvent) -> None:
        payload = _event_to_dict(event)
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO filing_events
                   (accession_number, ticker, filing_date, category, materiality_score, payload_json)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    event.filing.accession_number,
                    event.filing.company.ticker,
                    event.filing.filing_date.isoformat(),
                    event.primary_category,
                    event.materiality.score,
                    json.dumps(payload),
                ),
            )

    def load_range(self, since: date, until: date) -> List[FilingEvent]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT payload_json FROM filing_events
                   WHERE filing_date BETWEEN ? AND ?
                   ORDER BY materiality_score DESC, filing_date DESC""",
                (since.isoformat(), until.isoformat()),
            ).fetchall()
        return [_dict_to_event(json.loads(row[0])) for row in rows]


def _event_to_dict(event: FilingEvent) -> dict:
    d = asdict(event)
    d["filing"]["filing_date"] = event.filing.filing_date.isoformat()
    return d


def _dict_to_event(d: dict) -> FilingEvent:
    company = Company(**d["filing"]["company"])
    filing = Filing(
        company=company,
        accession_number=d["filing"]["accession_number"],
        filing_date=date.fromisoformat(d["filing"]["filing_date"]),
        form=d["filing"]["form"],
        items=d["filing"]["items"],
        primary_document=d["filing"]["primary_document"],
        filing_index_url=d["filing"]["filing_index_url"],
        document_url=d["filing"]["document_url"],
    )
    tags = [EventTag(**t) for t in d["tags"]]
    materiality = MaterialityScore(**d["materiality"])
    return FilingEvent(
        filing=filing,
        tags=tags,
        materiality=materiality,
        what_happened=d["what_happened"],
        why_it_matters=d["why_it_matters"],
        thesis_impact=d["thesis_impact"],
        excerpt=d.get("excerpt"),
        source=d.get("source", "template"),
    )
