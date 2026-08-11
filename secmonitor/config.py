from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import yaml

from secmonitor.models import Company

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_COMPANIES_FILE = REPO_ROOT / "config" / "companies.yaml"
DEFAULT_DATA_DIR = REPO_ROOT / "data"


@dataclass
class Settings:
    user_agent: str
    data_dir: Path = field(default_factory=lambda: DEFAULT_DATA_DIR)
    lookback_days: int = 7
    anthropic_api_key: str | None = None
    fetch_document_text: bool = True
    max_document_chars: int = 6000
    request_delay_seconds: float = 0.15  # stay well under SEC's fair-access rate limit

    @classmethod
    def from_env(cls) -> "Settings":
        user_agent = os.environ.get("SEC_EDGAR_USER_AGENT", "").strip()
        if not user_agent:
            raise RuntimeError(
                "SEC_EDGAR_USER_AGENT is not set. SEC requires a descriptive "
                "User-Agent header with contact info on every EDGAR request, "
                "e.g. export SEC_EDGAR_USER_AGENT='Jane Doe jane@example.com'. "
                "Requests without one are throttled or blocked outright."
            )
        return cls(
            user_agent=user_agent,
            data_dir=Path(os.environ.get("SECMONITOR_DATA_DIR", str(DEFAULT_DATA_DIR))),
            lookback_days=int(os.environ.get("SECMONITOR_LOOKBACK_DAYS", "7")),
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY") or None,
            fetch_document_text=os.environ.get("SECMONITOR_FETCH_TEXT", "1") != "0",
        )


def load_companies(path: Path = DEFAULT_COMPANIES_FILE) -> List[Company]:
    raw = yaml.safe_load(Path(path).read_text())
    sector = raw["sector"]
    companies = []
    for entry in raw["companies"]:
        companies.append(Company(ticker=entry["ticker"].upper(), name=entry["name"], sector=sector))
    return companies
