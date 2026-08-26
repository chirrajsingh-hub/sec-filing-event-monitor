from datetime import date

import pytest

from secmonitor import edgar_client
from secmonitor.edgar_client import (
    EdgarClient,
    build_filing_url,
    build_index_url,
    parse_recent_8k_filings,
    resolve_cik,
)


def _make_submissions_json():
    # Shaped like the real data.sec.gov/submissions/CIK##########.json payload.
    return {
        "cik": "320193",
        "filings": {
            "recent": {
                "form": ["8-K", "10-Q", "8-K", "8-K"],
                "filingDate": ["2026-08-05", "2026-08-01", "2026-07-20", "2026-08-08"],
                "reportDate": ["2026-08-05", "2026-06-30", "2026-07-19", ""],
                "accessionNumber": [
                    "0000320193-26-000101",
                    "0000320193-26-000099",
                    "0000320193-26-000090",
                    "0000320193-26-000110",
                ],
                "primaryDocument": [
                    "aapl-8k_20260805.htm",
                    "aapl-10q_20260801.htm",
                    "aapl-8k_20260720.htm",
                    "aapl-8k_20260808.htm",
                ],
                "items": ["2.02,9.01", "", "5.02", "1.01"],
            }
        },
    }


def test_parse_recent_8k_filings_filters_non_8k_forms():
    filings = parse_recent_8k_filings(
        _make_submissions_json(), ticker="AAPL", company="Apple Inc",
        since=date(2026, 1, 1),
    )
    assert all(True for _ in filings)  # sanity: doesn't raise
    assert len(filings) == 3  # the 10-Q is excluded


def test_parse_recent_8k_filings_filters_by_since_date():
    filings = parse_recent_8k_filings(
        _make_submissions_json(), ticker="AAPL", company="Apple Inc",
        since=date(2026, 8, 1),
    )
    dates = sorted(f.filing_date for f in filings)
    assert dates == [date(2026, 8, 5), date(2026, 8, 8)]


def test_parse_recent_8k_filings_parses_items_and_fields():
    filings = parse_recent_8k_filings(
        _make_submissions_json(), ticker="AAPL", company="Apple Inc",
        since=date(2026, 1, 1),
    )
    by_date = {f.filing_date: f for f in filings}
    earnings_filing = by_date[date(2026, 8, 5)]
    assert earnings_filing.items == ["2.02", "9.01"]
    assert earnings_filing.cik == "0000320193"
    assert earnings_filing.ticker == "AAPL"
    assert earnings_filing.report_date == date(2026, 8, 5)

    no_report_date_filing = by_date[date(2026, 8, 8)]
    assert no_report_date_filing.report_date is None


def test_build_filing_url_strips_leading_zeros_and_dashes():
    url = build_filing_url("0000320193", "0000320193-26-000101", "aapl-8k_20260805.htm")
    assert url == (
        "https://www.sec.gov/Archives/edgar/data/320193/"
        "000032019326000101/aapl-8k_20260805.htm"
    )


def test_build_index_url():
    url = build_index_url("0000320193", "0000320193-26-000101")
    assert url.endswith("0000320193-26-000101-index.htm")
    assert "320193" in url


def test_filing_record_url_properties_match_module_functions():
    filings = parse_recent_8k_filings(
        _make_submissions_json(), ticker="AAPL", company="Apple Inc",
        since=date(2026, 1, 1),
    )
    record = filings[0]
    assert record.edgar_url == build_filing_url(
        record.cik, record.accession_number, record.primary_document
    )
    assert record.index_url == build_index_url(record.cik, record.accession_number)


def test_resolve_cik_matches_case_insensitively():
    tickers_map = {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}}
    assert resolve_cik("aapl", tickers_map) == "0000320193"


def test_resolve_cik_raises_for_unknown_ticker():
    with pytest.raises(KeyError):
        resolve_cik("ZZZZ", {"0": {"cik_str": 1, "ticker": "AAPL", "title": "Apple Inc."}})


def test_edgar_client_requires_contact_email():
    with pytest.raises(ValueError):
        EdgarClient(contact_email="")
    with pytest.raises(ValueError):
        EdgarClient(contact_email="not-an-email")


def test_edgar_client_get_recent_8k_filings_end_to_end(monkeypatch):
    tickers_payload = {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}}
    submissions_payload = _make_submissions_json()

    calls = []

    def fake_get_json(url, headers):
        calls.append(url)
        assert "contact@example.com" in headers["User-Agent"]
        if "company_tickers" in url:
            return tickers_payload
        return submissions_payload

    monkeypatch.setattr(edgar_client, "_get_json", fake_get_json)
    client = EdgarClient(contact_email="contact@example.com", min_interval=0.0)

    filings = client.get_recent_8k_filings("AAPL", "Apple Inc", since=date(2026, 8, 1))

    assert len(filings) == 2
    assert len(calls) == 2  # tickers map fetched once, submissions once

    # Ticker map should be cached, not re-fetched on a second call.
    client.get_recent_8k_filings("AAPL", "Apple Inc", since=date(2026, 8, 1))
    assert len(calls) == 3  # +1 submissions call, no extra tickers-map call
