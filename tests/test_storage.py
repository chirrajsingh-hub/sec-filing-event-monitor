from datetime import date

from secmonitor.models import Company, EventTag, Filing, FilingEvent, MaterialityScore
from secmonitor.storage import EventStore


def _event(accession: str, ticker: str, filed: date, score: int) -> FilingEvent:
    company = Company(ticker=ticker, name=f"{ticker} Corp", sector="Semiconductors", cik="0000000001")
    filing = Filing(
        company=company,
        accession_number=accession,
        filing_date=filed,
        form="8-K",
        items=["5.02"],
        primary_document="form8k.htm",
        filing_index_url="https://www.sec.gov/index.htm",
        document_url="https://www.sec.gov/form8k.htm",
    )
    tag = EventTag(code="5.02", label="Departure/Election of Directors or Officers",
                    category="leadership_change", weight=3)
    materiality = MaterialityScore(score=score, level="Medium", rationale="test")
    return FilingEvent(
        filing=filing, tags=[tag], materiality=materiality,
        what_happened="x", why_it_matters="y", thesis_impact="z", source="template",
    )


def test_save_and_has_seen(tmp_path):
    store = EventStore(tmp_path / "test.db")
    event = _event("0000000001-26-000001", "AAA", date(2026, 8, 5), 3)

    assert store.has_seen(event.filing.accession_number) is False
    store.save(event)
    assert store.has_seen(event.filing.accession_number) is True


def test_load_range_filters_by_date_and_sorts_by_score(tmp_path):
    store = EventStore(tmp_path / "test.db")
    store.save(_event("acc-1", "AAA", date(2026, 8, 1), score=2))
    store.save(_event("acc-2", "BBB", date(2026, 8, 5), score=5))
    store.save(_event("acc-3", "CCC", date(2026, 7, 1), score=5))  # outside range

    events = store.load_range(date(2026, 8, 1), date(2026, 8, 8))
    assert [e.filing.accession_number for e in events] == ["acc-2", "acc-1"]


def test_roundtrip_preserves_fields(tmp_path):
    store = EventStore(tmp_path / "test.db")
    original = _event("acc-1", "AAA", date(2026, 8, 5), score=4)
    store.save(original)

    loaded = store.load_range(date(2026, 8, 1), date(2026, 8, 8))[0]
    assert loaded.filing.company.ticker == "AAA"
    assert loaded.tags[0].code == "5.02"
    assert loaded.materiality.score == 4
    assert loaded.what_happened == "x"
