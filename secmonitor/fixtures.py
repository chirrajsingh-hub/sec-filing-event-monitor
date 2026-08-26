"""Offline sample data: a hand-written week of 8-K-shaped events.

This mirrors `optvol.data.synthetic` in the sibling options-model project --
the honest reason it exists is that this sandbox's outbound network policy
blocks `sec.gov` and `data.sec.gov` (see `edgar_client`), so the pipeline,
scoring, and memo renderer need a deterministic, network-free path to
develop and test against. It also gives a stable demo: `--mode offline`
always produces the same memo shape without depending on there being real
newsworthy 8-Ks the week you happen to run it.

IMPORTANT: every event below is fabricated for demonstration purposes. CIKs
are placeholder values in the 9,000,000+ range, which is above any real SEC
CIK, specifically so they can never coincide with a real filer and the
generated EDGAR-style URLs never resolve to real content. Company tickers
and names are real (this is the point -- the taxonomy and scoring should
look plausible against real issuers) but the events attributed to them are
invented. The memo renderer stamps a "SAMPLE DATA" banner on any memo built
from this module; do not strip that banner when publishing output.
"""

from __future__ import annotations

from datetime import date, timedelta

from secmonitor.edgar_client import FilingRecord

# Each entry: (days_before_as_of, ticker, company, item_codes, headline, snippet)
_SAMPLE_EVENTS: list[tuple[int, str, str, list[str], str, str]] = [
    (1, "NVDA", "NVIDIA Corp", ["2.02", "9.01"],
     "NVIDIA reports quarterly results, raises next-quarter revenue outlook",
     "Revenue for the quarter exceeded the high end of prior guidance on "
     "data-center demand; management raised next-quarter guidance above "
     "the analyst consensus range."),
    (2, "AMD", "Advanced Micro Devices Inc", ["1.01"],
     "AMD enters definitive agreement to acquire an AI-inference startup",
     "The company agreed to acquire a privately held AI-inference software "
     "startup in an all-cash definitive agreement to acquire the target's "
     "technology and engineering team, subject to customary closing "
     "conditions."),
    (2, "TXN", "Texas Instruments Inc", ["2.02"],
     "Texas Instruments reports results, cuts guidance on soft industrial demand",
     "Management cuts guidance for the coming quarter, citing continued "
     "softness in industrial and automotive end markets; preliminary "
     "results were below the prior outlook range."),
    (3, "ON", "ON Semiconductor Corp", ["2.01", "9.01"],
     "ON Semiconductor completes previously announced acquisition of SiC wafer supplier",
     "The company completed its previously announced acquisition of a "
     "silicon-carbide wafer supplier, expanding in-house substrate "
     "capacity for its power semiconductor business."),
    (1, "QRVO", "Qorvo Inc", ["5.02"],
     "Qorvo announces resignation of Chief Financial Officer",
     "The company announced the resignation of its Chief Financial "
     "Officer, effective immediately; the board has begun a search for a "
     "successor and named an interim CFO."),
    (4, "LRCX", "Lam Research Corp", ["5.02"],
     "Lam Research names successor Chief Executive Officer in planned transition",
     "The board elected a new Chief Executive Officer effective at the "
     "next fiscal year, as part of a previously disclosed multi-year "
     "succession plan; the current CEO will remain as executive chair."),
    (3, "MU", "Micron Technology Inc", ["2.03"],
     "Micron prices $2.0 billion senior notes due 2033",
     "The company priced an offering of senior notes due 2033 to fund "
     "capacity expansion at existing fabrication sites and for general "
     "corporate purposes."),
    (5, "SITM", "SiTime Corp", ["4.02"],
     "SiTime discloses non-reliance on previously issued financial statements",
     "The audit committee concluded that previously issued financial "
     "statements should no longer be relied upon due to a material "
     "weakness identified in revenue-recognition controls; the company "
     "will restate the affected periods."),
    (2, "DIOD", "Diodes Inc", ["1.05"],
     "Diodes Incorporated discloses cybersecurity incident involving unauthorized access",
     "The company identified unauthorized access to a subset of its IT "
     "systems and engaged outside forensic experts; the company is "
     "assessing the scope of affected data and has notified law "
     "enforcement."),
    (6, "POWI", "Power Integrations Inc", ["2.06"],
     "Power Integrations records goodwill impairment charge",
     "The company recorded a non-cash goodwill impairment charge related "
     "to a prior acquisition, reflecting a reduced long-term revenue "
     "outlook for that reporting unit."),
    (4, "RMBS", "Rambus Inc", ["8.01"],
     "Rambus files patent infringement lawsuit against a competitor",
     "The company filed a lawsuit alleging patent infringement by a "
     "competitor's memory-interface chip products and is seeking damages "
     "and injunctive relief."),
    (5, "ALGM", "Allegro MicroSystems Inc", ["8.01"],
     "Allegro MicroSystems receives regulatory inquiry regarding a supply agreement",
     "The company received a request for information from a regulatory "
     "agency regarding a long-term supply agreement with a large "
     "automotive customer; the company is cooperating with the inquiry."),
    (1, "STM", "STMicroelectronics NV", ["1.01"],
     "STMicroelectronics enters new revolving credit facility",
     "The company entered into a new multi-year revolving credit "
     "agreement with a syndicate of banks, replacing its prior facility "
     "and increasing available liquidity."),
    (3, "KLAC", "KLA Corp", ["2.02", "7.01"],
     "KLA reports in-line quarterly results",
     "Results for the quarter were in line with prior guidance; "
     "management reiterated its outlook for the fiscal year in "
     "supplemental investor materials furnished under Item 7.01."),
    (6, "ENTG", "Entegris Inc", ["2.05"],
     "Entegris announces restructuring plan including facility consolidation",
     "The company announced a restructuring plan involving the "
     "consolidation of two manufacturing facilities and an associated "
     "workforce reduction, with expected annualized cost savings."),
    (2, "WOLF", "Wolfspeed Inc", ["5.07"],
     "Wolfspeed discloses annual meeting voting results",
     "The company disclosed voting results from its annual meeting of "
     "stockholders, including the election of directors and ratification "
     "of the independent auditor."),
    (5, "NXPI", "NXP Semiconductors NV", ["3.02"],
     "NXP Semiconductors discloses unregistered sale of equity securities",
     "The company issued shares upon conversion of outstanding notes in a "
     "transaction exempt from registration under the Securities Act."),
    (4, "MRVL", "Marvell Technology Inc", ["4.01"],
     "Marvell Technology dismisses independent registered public accounting firm",
     "The audit committee dismissed the company's independent registered "
     "public accounting firm and engaged a new firm for the current "
     "fiscal year; the change was not the result of a disagreement on "
     "accounting matters, per the filing."),
]


def sample_filings(as_of: date | None = None) -> list[tuple[FilingRecord, str, str]]:
    """Return synthetic (FilingRecord, headline, snippet) tuples for a demo week.

    Filing dates are computed relative to `as_of` (default: today) so a
    default `weeks_back=1` pipeline run always picks up every fixture,
    regardless of when the demo is actually run.
    """
    as_of = as_of or date.today()
    records: list[tuple[FilingRecord, str, str]] = []
    for i, (days_before, ticker, company, items, headline, snippet) in enumerate(_SAMPLE_EVENTS):
        filing_date = as_of - timedelta(days=days_before)
        cik = f"{9_000_001 + i:010d}"
        accession_number = f"{cik}-{filing_date.strftime('%y')}-{i + 1:06d}"
        primary_document = f"{ticker.lower()}-8k_{filing_date.strftime('%Y%m%d')}.htm"
        record = FilingRecord(
            ticker=ticker,
            company=company,
            cik=cik,
            accession_number=accession_number,
            filing_date=filing_date,
            report_date=filing_date,
            items=items,
            primary_document=primary_document,
        )
        records.append((record, headline, snippet))
    return records
