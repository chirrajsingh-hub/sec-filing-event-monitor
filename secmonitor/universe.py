"""The tracked company universe.

Ticker + legal name only -- CIKs are resolved at run time from EDGAR's
`company_tickers.json` (see `edgar_client.resolve_cik`) rather than
hard-coded here, since ticker->CIK mappings occasionally change (spinoffs,
relistings) and the live lookup is a single cached request per run.

30 large- and mid-cap semiconductor and semiconductor-equipment names,
chosen for a sector with a genuinely diverse event mix over any given
quarter: earnings-driven moves, M&A (both strategic and antitrust-blocked),
export-control and litigation exposure, capacity-driven debt financing, and
periodic leadership turnover. Swap this list (or add a second `Sector`) to
point the monitor at a different part of the market.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Company:
    ticker: str
    name: str


@dataclass(frozen=True)
class Sector:
    name: str
    companies: tuple[Company, ...]

    @property
    def tickers(self) -> list[str]:
        return [c.ticker for c in self.companies]


SEMICONDUCTORS = Sector(
    name="Semiconductors & Semiconductor Equipment",
    companies=(
        Company("NVDA", "NVIDIA Corp"),
        Company("AMD", "Advanced Micro Devices Inc"),
        Company("INTC", "Intel Corp"),
        Company("QCOM", "Qualcomm Inc"),
        Company("AVGO", "Broadcom Inc"),
        Company("TXN", "Texas Instruments Inc"),
        Company("MU", "Micron Technology Inc"),
        Company("AMAT", "Applied Materials Inc"),
        Company("LRCX", "Lam Research Corp"),
        Company("KLAC", "KLA Corp"),
        Company("ASML", "ASML Holding NV"),
        Company("ADI", "Analog Devices Inc"),
        Company("MCHP", "Microchip Technology Inc"),
        Company("ON", "ON Semiconductor Corp"),
        Company("SWKS", "Skyworks Solutions Inc"),
        Company("QRVO", "Qorvo Inc"),
        Company("MRVL", "Marvell Technology Inc"),
        Company("MPWR", "Monolithic Power Systems Inc"),
        Company("WOLF", "Wolfspeed Inc"),
        Company("NXPI", "NXP Semiconductors NV"),
        Company("STM", "STMicroelectronics NV"),
        Company("TER", "Teradyne Inc"),
        Company("ENTG", "Entegris Inc"),
        Company("CRUS", "Cirrus Logic Inc"),
        Company("DIOD", "Diodes Inc"),
        Company("SLAB", "Silicon Laboratories Inc"),
        Company("POWI", "Power Integrations Inc"),
        Company("RMBS", "Rambus Inc"),
        Company("SITM", "SiTime Corp"),
        Company("ALGM", "Allegro MicroSystems Inc"),
    ),
)

DEFAULT_SECTOR = SEMICONDUCTORS
