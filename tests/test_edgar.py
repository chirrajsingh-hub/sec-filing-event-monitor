import json
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

from secmonitor.edgar import EdgarClient
from secmonitor.models import Company

FIXTURES = Path(__file__).parent / "fixtures"


def _fake_response(payload):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = payload
    resp.text = json.dumps(payload)
    return resp


def test_iter_recent_8k_filters_form_and_date_window():
    submissions = json.loads((FIXTURES / "sample_submissions.json").read_text())
    client = EdgarClient(user_agent="Test test@example.com")
    client.session.get = MagicMock(return_value=_fake_response(submissions))

    company = Company(ticker="TEST", name="Test Semi Corp", sector="Semiconductors", cik="0001045810")
    filings = list(client.iter_recent_8k(company, since=date(2026, 8, 1), until=date(2026, 8, 11)))

    assert len(filings) == 2
    assert {f.accession_number for f in filings} == {
        "0001045810-26-000001",
        "0001045810-26-000002",
    }
    first = next(f for f in filings if f.accession_number == "0001045810-26-000001")
    assert first.items == ["5.02", "9.01"]
    assert first.document_url == (
        "https://www.sec.gov/Archives/edgar/data/1045810/000104581026000001/form8k1.htm"
    )


def test_iter_recent_8k_excludes_non_8k_and_out_of_window():
    submissions = json.loads((FIXTURES / "sample_submissions.json").read_text())
    client = EdgarClient(user_agent="Test test@example.com")
    client.session.get = MagicMock(return_value=_fake_response(submissions))

    company = Company(ticker="TEST", name="Test Semi Corp", sector="Semiconductors", cik="0001045810")
    filings = list(client.iter_recent_8k(company, since=date(2026, 8, 6), until=date(2026, 8, 11)))

    assert len(filings) == 1
    assert filings[0].accession_number == "0001045810-26-000002"


def test_resolve_companies_raises_on_missing_ticker():
    client = EdgarClient(user_agent="Test test@example.com")
    client.session.get = MagicMock(return_value=_fake_response({"0": {"cik_str": 1, "ticker": "AAA", "title": "AAA Inc"}}))

    companies = [Company(ticker="ZZZZ", name="Unknown Co", sector="Semiconductors")]
    try:
        client.resolve_companies(companies)
        assert False, "expected EdgarError"
    except Exception as exc:
        assert "ZZZZ" in str(exc)
