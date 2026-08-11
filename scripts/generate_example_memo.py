"""Regenerates examples/sample_weekly_memo.md by driving the real pipeline
(events.py -> scoring.py -> summarizer.py -> memo.py) against mocked EDGAR
responses. This is how you preview the memo format without live network
access to sec.gov -- the company names/tickers are real but the filing
content here is fabricated for demonstration only. Not part of the
installed `secmonitor` package; run directly with `python scripts/generate_example_memo.py`.
"""
import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from secmonitor.config import Settings
from secmonitor.edgar import EdgarClient
from secmonitor.models import Company
from secmonitor.pipeline import run_pipeline
from secmonitor.storage import EventStore
from secmonitor.memo import render_weekly_memo
import secmonitor.pipeline as pipeline_mod

TICKER_MAP = {
    "0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA Corporation"},
    "1": {"cik_str": 2488, "ticker": "AMD", "title": "Advanced Micro Devices, Inc."},
    "2": {"cik_str": 50863, "ticker": "INTC", "title": "Intel Corporation"},
    "3": {"cik_str": 1090872, "ticker": "MRVL", "title": "Marvell Technology, Inc."},
    "4": {"cik_str": 1109357, "ticker": "MU", "title": "Micron Technology, Inc."},
}

SUBMISSIONS = {
    "1045810": {"filings": {"recent": {  # NVDA - earnings
        "accessionNumber": ["0001045810-26-000101"], "filingDate": ["2026-08-06"],
        "form": ["8-K"], "primaryDocument": ["nvda8k.htm"], "items": ["2.02,9.01"],
    }}},
    "2488": {"filings": {"recent": {  # AMD - abrupt CFO departure
        "accessionNumber": ["0000002488-26-000202"], "filingDate": ["2026-08-04"],
        "form": ["8-K"], "primaryDocument": ["amd8k.htm"], "items": ["5.02"],
    }}},
    "50863": {"filings": {"recent": {  # INTC - Item 8.01 catch-all that is actually M&A news
        "accessionNumber": ["0000050863-26-000303"], "filingDate": ["2026-08-07"],
        "form": ["8-K"], "primaryDocument": ["intc8k.htm"], "items": ["8.01"],
    }}},
    "1090872": {"filings": {"recent": {  # MRVL - debt financing
        "accessionNumber": ["0001090872-26-000404"], "filingDate": ["2026-08-05"],
        "form": ["8-K"], "primaryDocument": ["mrvl8k.htm"], "items": ["2.03"],
    }}},
    "1109357": {"filings": {"recent": {  # MU - restatement (critical)
        "accessionNumber": ["0001109357-26-000505"], "filingDate": ["2026-08-08"],
        "form": ["8-K"], "primaryDocument": ["mu8k.htm"], "items": ["4.02"],
    }}},
}

DOC_TEXT = {
    "nvda8k.htm": "<html><body>NVIDIA Corporation today reported financial results for its fiscal second quarter. "
                  "Revenue was $35.1 billion, up from prior guidance. The company issued forward guidance for the "
                  "next quarter above consensus estimates.</body></html>",
    "amd8k.htm": "<html><body>Advanced Micro Devices, Inc. announced that its Chief Financial Officer notified the "
                 "Company of her resignation, effective immediately, to pursue another opportunity. The Company has "
                 "commenced a search for a successor.</body></html>",
    "intc8k.htm": "<html><body>Intel Corporation entered into a definitive agreement to acquire a privately held "
                  "AI accelerator design firm for approximately $1.2 billion in cash and stock, subject to customary "
                  "closing conditions and regulatory approval.</body></html>",
    "mrvl8k.htm": "<html><body>Marvell Technology, Inc. entered into a new $750 million term loan facility to "
                  "refinance existing indebtedness and for general corporate purposes.</body></html>",
    "mu8k.htm": "<html><body>Micron Technology, Inc. determined that its previously issued financial statements "
                "for fiscal 2025 should no longer be relied upon due to a material weakness identified in revenue "
                "recognition for certain multi-year supply agreements. The Audit Committee is overseeing a "
                "restatement.</body></html>",
}


def fake_get(url, timeout=20):
    resp = MagicMock()
    resp.status_code = 200
    if "company_tickers.json" in url:
        resp.json.return_value = TICKER_MAP
        return resp
    if "data.sec.gov/submissions" in url:
        cik = url.split("CIK")[1].split(".json")[0].lstrip("0") or "0"
        resp.json.return_value = SUBMISSIONS[cik]
        return resp
    doc_name = url.rsplit("/", 1)[-1]
    resp.text = DOC_TEXT.get(doc_name, "<html><body>No content.</body></html>")
    return resp


def main() -> None:
    companies = [Company(ticker=e["ticker"], name=e["title"], sector="Semiconductors")
                 for e in TICKER_MAP.values()]

    settings = Settings(user_agent="Example Generator example@example.com",
                         data_dir=Path("/tmp/secmonitor-example-data"))
    store = EventStore(settings.data_dir / "example.db")

    client = EdgarClient(user_agent=settings.user_agent, cache_dir=settings.data_dir / "cache")
    client.session.get = fake_get

    orig_client_cls = pipeline_mod.EdgarClient
    pipeline_mod.EdgarClient = lambda **kwargs: client
    try:
        events = run_pipeline(settings, since=date(2026, 8, 1), until=date(2026, 8, 8),
                               companies=companies, store=store)
    finally:
        pipeline_mod.EdgarClient = orig_client_cls

    memo = render_weekly_memo(events, date(2026, 8, 1), date(2026, 8, 8), sector="Semiconductors")
    out_path = REPO_ROOT / "examples" / "sample_weekly_memo.md"
    disclaimer = (
        "> **⚠ Illustrative example — not real filings.** This memo was generated by running the actual\n"
        "> `secmonitor` pipeline (events.py → scoring.py → summarizer.py → memo.py) against mocked EDGAR\n"
        "> responses, so you can see the real output format without needing live network access. The company\n"
        "> names/tickers are real, but the filing dates, item codes, and quoted filing text are fabricated for\n"
        "> demonstration only and do not reflect any actual disclosure by these companies. See\n"
        "> `scripts/generate_example_memo.py` for exactly how it was produced; run `secmonitor fetch` /\n"
        "> `secmonitor memo` against live EDGAR to get the real thing.\n\n"
    )
    out_path.write_text(disclaimer + memo)
    print(f"Generated {len(events)} events -> {out_path}")


if __name__ == "__main__":
    main()
