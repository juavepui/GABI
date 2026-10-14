"""Reviewed, versioned research ledgers shipped with the package (index membership and ticker nominations)."""

import json
from functools import cache
from pathlib import Path

from gabi.domain.research import ticker_corrections

RESOURCES = Path(__file__).resolve().parents[2] / "resources"
MEMBERSHIP_LEDGER = RESOURCES / "sp500_extension.json"
NOMINATION_PATHS = (RESOURCES / "historical_identity_corrections_2010_2015.json",
                    RESOURCES / "historical_identity_corrections_2016_2025.json")


def membership_ledger() -> dict:
    return json.loads(MEMBERSHIP_LEDGER.read_text(encoding="utf-8"))


@cache
def identity_nominations() -> tuple[dict, ...]:
    """Reviewed label -> CIK nominations; SEC evidence must still confirm them."""
    rows = [row for path in NOMINATION_PATHS for row in json.loads(path.read_text(encoding="utf-8"))["entries"]]
    return ticker_corrections.parse_nominations(rows)
