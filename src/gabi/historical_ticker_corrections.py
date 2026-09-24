"""Small ledger of independently reviewed historical ticker labels.

Community snapshots may apply a later ticker retrospectively. Corrections are
date-bounded, source-attributed and applied at query time; raw files stay intact.
"""

from datetime import date

WLP_START = "2009-12-01"  # SEC-filed contemporaneous NYSE: WLP announcement.
WLP_END = "2014-12-03"  # MIAX effective trading date for WLP -> ANTM.
WLP_SOURCES = [
    "https://www.sec.gov/Archives/edgar/data/1156039/000119312509244519/dex991.htm",
    "https://www.miaxglobal.com/alert/2014/12/02/miax-corporate-action-alert-wellpoint-inc-wlp-name-and-symbol-change-anthem",
]


def correct_symbols(symbols: set[str], as_of: str) -> tuple[set[str], list[dict]]:
    """Correct a documented retrospective label, never invent membership."""
    day = date.fromisoformat(as_of).isoformat()
    result = set(symbols)
    changes = []
    if WLP_START <= day < WLP_END and "ANTM" in result:
        if "WLP" in result:
            raise ValueError(f"Both WLP and ANTM occur in historical membership on {day}")
        result.remove("ANTM")
        result.add("WLP")
        changes.append({"reported_symbol": "ANTM", "historical_symbol": "WLP",
                        "valid_from": WLP_START, "valid_to": WLP_END,
                        "source_urls": WLP_SOURCES})
    return result, changes
