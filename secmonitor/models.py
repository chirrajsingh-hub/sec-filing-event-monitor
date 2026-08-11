from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional


@dataclass
class Company:
    ticker: str
    name: str
    sector: str
    cik: Optional[str] = None  # 10-digit zero-padded CIK, resolved at runtime


@dataclass
class EventTag:
    code: str          # SEC 8-K item code, e.g. "5.02"
    label: str          # human label, e.g. "Departure/Election of Directors or Officers"
    category: str        # normalized bucket, e.g. "leadership_change"
    weight: int         # base materiality weight, 1-5


@dataclass
class Filing:
    company: Company
    accession_number: str
    filing_date: date
    form: str
    items: List[str]           # raw item codes as reported by EDGAR
    primary_document: str
    filing_index_url: str
    document_url: str


@dataclass
class MaterialityScore:
    score: int        # 1-5
    level: str         # Informational / Low / Medium / High / Critical
    rationale: str


@dataclass
class FilingEvent:
    filing: Filing
    tags: List[EventTag]
    materiality: MaterialityScore
    what_happened: str
    why_it_matters: str
    thesis_impact: str
    excerpt: Optional[str] = None
    source: str = "template"  # "template" or "llm", tracks how the narrative was produced

    @property
    def primary_category(self) -> str:
        if not self.tags:
            return "other"
        return max(self.tags, key=lambda t: t.weight).category
