"""Live EDGAR client.

Two endpoint families, both free and unauthenticated:

  https://www.sec.gov/files/company_tickers.json
      A single JSON blob mapping every registrant's ticker to its CIK.
      Fetched once per run and cached in-process.

  https://data.sec.gov/submissions/CIK{10-digit CIK}.json
      Per-company filing history: form type, filing date, accession
      number, primary document, and -- for 8-Ks -- the comma-separated
      Item codes, all in `filings.recent` (paginated further back via
      `filings.files`, which this client doesn't need for a weekly window).

SEC's fair-access policy (17 CFR 240.15) requires a descriptive
User-Agent identifying the requester, and asks for no more than ~10
requests/second; this client sends `contact_email` in every User-Agent
header and sleeps between requests well under that limit.

The HTTP calls are isolated in `_get_json` / `EdgarClient` methods so the
parsing logic (`parse_recent_8k_filings`, `build_filing_url`) stays pure
and unit-testable without a live connection -- see
`tests/test_sec_edgar_client.py`, which exercises the parser against a
hand-built JSON fixture shaped like the real API response.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date, datetime

import requests

COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:0>10}.json"
ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"

FORM_8K = "8-K"
MIN_REQUEST_INTERVAL_SECONDS = 0.15  # well under SEC's ~10 req/s guidance


@dataclass(frozen=True)
class FilingRecord:
    ticker: str
    company: str
    cik: str
    accession_number: str
    filing_date: date
    report_date: date | None
    items: list[str]
    primary_document: str

    @property
    def edgar_url(self) -> str:
        return build_filing_url(self.cik, self.accession_number, self.primary_document)

    @property
    def index_url(self) -> str:
        return build_index_url(self.cik, self.accession_number)


def build_filing_url(cik: str, accession_number: str, primary_document: str) -> str:
    cik_no_zeros = str(int(cik))
    accession_no_dashes = accession_number.replace("-", "")
    return f"{ARCHIVES_BASE}/{cik_no_zeros}/{accession_no_dashes}/{primary_document}"


def build_index_url(cik: str, accession_number: str) -> str:
    cik_no_zeros = str(int(cik))
    accession_no_dashes = accession_number.replace("-", "")
    return f"{ARCHIVES_BASE}/{cik_no_zeros}/{accession_no_dashes}/{accession_number}-index.htm"


def resolve_cik(ticker: str, tickers_map: dict) -> str:
    """Look up a CIK from the parsed `company_tickers.json` payload.

    That payload is a dict of dicts keyed by arbitrary integer strings,
    e.g. `{"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}}`.
    """
    ticker_upper = ticker.upper()
    for entry in tickers_map.values():
        if entry.get("ticker", "").upper() == ticker_upper:
            return str(entry["cik_str"]).zfill(10)
    raise KeyError(f"No CIK found for ticker {ticker!r}")


def parse_recent_8k_filings(
    submissions_json: dict,
    ticker: str,
    company: str,
    since: date,
) -> list[FilingRecord]:
    """Extract 8-K filings on or after `since` from a submissions.json payload."""
    cik = str(submissions_json["cik"]).zfill(10)
    recent = submissions_json["filings"]["recent"]

    n = len(recent["form"])
    records: list[FilingRecord] = []
    for i in range(n):
        if recent["form"][i] != FORM_8K:
            continue

        filing_date = datetime.strptime(recent["filingDate"][i], "%Y-%m-%d").date()
        if filing_date < since:
            continue

        report_date_raw = recent.get("reportDate", [""] * n)[i]
        report_date = (
            datetime.strptime(report_date_raw, "%Y-%m-%d").date() if report_date_raw else None
        )

        items_raw = recent.get("items", [""] * n)[i]
        items = [code.strip() for code in items_raw.split(",") if code.strip()]

        records.append(
            FilingRecord(
                ticker=ticker,
                company=company,
                cik=cik,
                accession_number=recent["accessionNumber"][i],
                filing_date=filing_date,
                report_date=report_date,
                items=items,
                primary_document=recent["primaryDocument"][i],
            )
        )
    return records


def _get_json(url: str, headers: dict) -> dict:
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()


class EdgarClient:
    """Thin, rate-limited wrapper around the two EDGAR endpoints above."""

    def __init__(self, contact_email: str, min_interval: float = MIN_REQUEST_INTERVAL_SECONDS):
        if not contact_email or "@" not in contact_email:
            raise ValueError(
                "EdgarClient requires a real contact_email for the SEC fair-access "
                "User-Agent header -- see https://www.sec.gov/os/webmaster-faq#developers"
            )
        self.headers = {"User-Agent": f"secmonitor research tool ({contact_email})"}
        self.min_interval = min_interval
        self._last_request_at = 0.0
        self._tickers_map: dict | None = None

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last_request_at = time.monotonic()

    def _get(self, url: str) -> dict:
        self._throttle()
        return _get_json(url, self.headers)

    def get_tickers_map(self) -> dict:
        if self._tickers_map is None:
            self._tickers_map = self._get(COMPANY_TICKERS_URL)
        return self._tickers_map

    def resolve_cik(self, ticker: str) -> str:
        return resolve_cik(ticker, self.get_tickers_map())

    def get_submissions(self, cik: str) -> dict:
        return self._get(SUBMISSIONS_URL.format(cik=cik))

    def get_recent_8k_filings(self, ticker: str, company: str, since: date) -> list[FilingRecord]:
        cik = self.resolve_cik(ticker)
        submissions = self.get_submissions(cik)
        return parse_recent_8k_filings(submissions, ticker, company, since)
