"""Thin client around the free, public SEC EDGAR JSON/HTML endpoints.

No API key is required, but SEC's fair-access policy requires every request
to carry a descriptive `User-Agent` (name + contact email) and asks
automated clients to stay under ~10 requests/second. See
https://www.sec.gov/os/webmaster-faq#developers for the current guidance.

Endpoints used:
  - https://www.sec.gov/files/company_tickers.json       ticker -> CIK map
  - https://data.sec.gov/submissions/CIK##########.json    per-company filing history
  - https://www.sec.gov/Archives/edgar/data/...             filing documents

This module is deliberately dependency-light (stdlib + requests) so the
pipeline is easy to run anywhere, including offline against cached/mocked
data for tests.
"""

from __future__ import annotations

import html
import json
import re
import time
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import requests

from secmonitor.models import Company, Filing

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


class EdgarError(RuntimeError):
    """Raised for network/parsing failures against EDGAR, with enough context
    to diagnose without re-running under a debugger."""


class EdgarClient:
    def __init__(self, user_agent: str, request_delay_seconds: float = 0.15, cache_dir: Optional[Path] = None):
        if not user_agent:
            raise ValueError("EdgarClient requires a descriptive User-Agent (name + contact email).")
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": user_agent,
            "Accept-Encoding": "gzip, deflate",
        })
        self.request_delay_seconds = request_delay_seconds
        self.cache_dir = cache_dir
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get(self, url: str) -> requests.Response:
        try:
            resp = self.session.get(url, timeout=20)
        except requests.RequestException as exc:
            raise EdgarError(f"Request to {url} failed: {exc}") from exc
        time.sleep(self.request_delay_seconds)
        if resp.status_code == 429:
            raise EdgarError(f"Rate limited by EDGAR on {url}. Slow down request_delay_seconds.")
        if resp.status_code != 200:
            raise EdgarError(f"EDGAR returned HTTP {resp.status_code} for {url}: {resp.text[:200]}")
        return resp

    def get_ticker_cik_map(self, force_refresh: bool = False) -> Dict[str, str]:
        """Returns {TICKER: '0001234567'} for every registrant EDGAR knows about."""
        cache_path = self.cache_dir / "ticker_cik_map.json" if self.cache_dir else None
        if cache_path and cache_path.exists() and not force_refresh:
            return json.loads(cache_path.read_text())

        resp = self._get(TICKERS_URL)
        raw = resp.json()  # {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}, ...}
        mapping = {entry["ticker"].upper(): f"{int(entry['cik_str']):010d}" for entry in raw.values()}

        if cache_path:
            cache_path.write_text(json.dumps(mapping))
        return mapping

    def resolve_companies(self, companies: List[Company], force_refresh: bool = False) -> List[Company]:
        cik_map = self.get_ticker_cik_map(force_refresh=force_refresh)
        resolved = []
        missing = []
        for company in companies:
            cik = cik_map.get(company.ticker.upper())
            if cik is None:
                missing.append(company.ticker)
                continue
            resolved.append(Company(ticker=company.ticker, name=company.name, sector=company.sector, cik=cik))
        if missing:
            raise EdgarError(
                f"Could not resolve CIK for ticker(s): {', '.join(missing)}. "
                "Check config/companies.yaml for typos or delisted symbols."
            )
        return resolved

    def get_company_submissions(self, company: Company) -> dict:
        if not company.cik:
            raise ValueError(f"{company.ticker} has no resolved CIK; call resolve_companies() first.")
        url = SUBMISSIONS_URL.format(cik=int(company.cik))
        return self._get(url).json()

    def iter_recent_8k(self, company: Company, since: date, until: date) -> Iterable[Filing]:
        """Yields Filing objects for 8-Ks filed on [since, until] (inclusive).

        Only scans the `filings.recent` window returned by the submissions
        endpoint, which comfortably covers the trailing weeks/months a weekly
        monitor cares about. A backfill job covering years of history would
        additionally need to paginate through `filings.files`.
        """
        submissions = self.get_company_submissions(company)
        recent = submissions.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        accession_numbers = recent.get("accessionNumber", [])
        filing_dates = recent.get("filingDate", [])
        primary_docs = recent.get("primaryDocument", [])
        items_list = recent.get("items", [])

        for i, form in enumerate(forms):
            if form != "8-K":
                continue
            filed = datetime.strptime(filing_dates[i], "%Y-%m-%d").date()
            if not (since <= filed <= until):
                continue

            accession = accession_numbers[i]
            accession_nodash = accession.replace("-", "")
            primary_document = primary_docs[i] if i < len(primary_docs) else ""
            item_codes = [c.strip() for c in items_list[i].split(",")] if i < len(items_list) and items_list[i] else []

            cik_int = int(company.cik)
            document_url = f"{ARCHIVES_BASE}/{cik_int}/{accession_nodash}/{primary_document}"
            filing_index_url = f"{ARCHIVES_BASE}/{cik_int}/{accession_nodash}/{accession}-index.htm"

            yield Filing(
                company=company,
                accession_number=accession,
                filing_date=filed,
                form=form,
                items=item_codes,
                primary_document=primary_document,
                filing_index_url=filing_index_url,
                document_url=document_url,
            )

    def fetch_document_text(self, filing: Filing, max_chars: int = 6000) -> Optional[str]:
        """Best-effort plain-text extraction of a filing's primary document.
        Returns None rather than raising if the document can't be fetched, since
        text is used to enrich scoring/summaries, not required for the pipeline
        to produce output."""
        if not filing.document_url:
            return None
        try:
            resp = self._get(filing.document_url)
        except EdgarError:
            return None
        text = _strip_html(resp.text)
        return text[:max_chars]


def _strip_html(raw_html: str) -> str:
    no_tags = _TAG_RE.sub(" ", raw_html)
    unescaped = html.unescape(no_tags)
    return _WS_RE.sub(" ", unescaped).strip()
