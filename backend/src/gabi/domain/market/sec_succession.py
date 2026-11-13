"""Reviewed SEC registrant successions for the current ticker map (#202).

In a holding reorganization the SEC ticker file moves the ticker to the new
registrant before it files any annual report, while the predecessor keeps
filing as a subsidiary. Until the successor files its own 10-K, the current
symbol reads the predecessor's statements. Each entry is reviewed against the
successor's 8-K12B; nothing here is inferred from names or ticker reuse.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Succession:
    predecessor: str
    effective: str
    evidence: str


SUCCESSIONS: dict[str, Succession] = {
    # ExxonMobil Holdings Corp took XOM; Exxon Mobil Corp delisted (25-NSE 2026-07-02) and keeps filing.
    "0002115436": Succession("0000034088", "2026-07-01", "8-K12B 0001193125-26-291990"),
}


def files_annual_report(filings: dict) -> bool:
    """Whether the registrant's EDGAR submissions include a 10-K of its own."""
    forms = filings.get("filings", {}).get("recent", {}).get("form", [])
    return any(form in ("10-K", "10-K/A") for form in forms)
