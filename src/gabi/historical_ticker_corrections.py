"""Small ledger of independently reviewed historical ticker labels.

Community snapshots may apply a later ticker retrospectively. Corrections are
date-bounded, source-attributed and applied at query time; raw files stay intact.
"""

import json
from datetime import date
from functools import cache
from pathlib import Path

NOMINATIONS_PATH = Path(__file__).with_name("resources") / "historical_identity_corrections_2010_2015.json"
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


@cache
def identity_nominations() -> tuple[dict, ...]:
    """Reviewed label -> CIK nominations; SEC evidence must still confirm them."""
    payload = json.loads(NOMINATIONS_PATH.read_text(encoding="utf-8"))
    entries = []
    for row in payload["entries"]:
        start, end = date.fromisoformat(row["valid_from"]), date.fromisoformat(row["valid_to"])
        if start >= end or not row["sec_tickers"] or len(row["cik"]) != 10 or not row["cik"].isdigit():
            raise ValueError(f"Invalid identity nomination: {row}")
        entries.append({**row, "sec_tickers": tuple(row["sec_tickers"]),
                        "evidence_window_days": int(row.get("evidence_window_days", 0))})
    labels: dict[str, list[dict]] = {}
    for row in entries:
        for other in labels.get(row["label"], []):
            if row["valid_from"] < other["valid_to"] and other["valid_from"] < row["valid_to"]:
                raise ValueError(f"Overlapping identity nominations for {row['label']}")
        labels.setdefault(row["label"], []).append(row)
    return tuple(entries)


def apply_nominations(by_symbol: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """Replace community candidates only inside each nomination interval."""
    result = {symbol: list(rows) for symbol, rows in by_symbol.items()}
    for entry in identity_nominations():
        if entry.get("price_only"):
            continue
        kept = []
        for row in result.get(entry["label"], []):
            if row.get("nomination"):
                kept.append(row)
                continue
            if row["start"] < entry["valid_from"]:
                kept.append({**row, "end": min(row["end"], entry["valid_from"])})
            if row["end"] > entry["valid_to"]:
                kept.append({**row, "start": max(row["start"], entry["valid_to"])})
        kept.append({"cik": entry["cik"], "name": None, "start": entry["valid_from"],
                     "end": entry["valid_to"], "nomination": entry})
        result[entry["label"]] = [row for row in kept if row["start"] < row["end"]]
    return result
