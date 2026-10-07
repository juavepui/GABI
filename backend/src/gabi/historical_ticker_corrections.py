"""Small ledger of independently reviewed historical ticker labels.

Community snapshots may apply a later ticker retrospectively. Corrections are
date-bounded, source-attributed and applied at query time; raw files stay intact.
"""

import json
from functools import cache
from pathlib import Path

from gabi.domain.research import ticker_corrections
from gabi.domain.research.ticker_corrections import WLP_END as WLP_END
from gabi.domain.research.ticker_corrections import WLP_START as WLP_START

NOMINATIONS_PATH = Path(__file__).with_name("resources") / "historical_identity_corrections_2010_2015.json"
# #34: same ledger format for 2016-2025; entries are date-bounded, so both load together.
NOMINATION_PATHS = (NOMINATIONS_PATH,
                    Path(__file__).with_name("resources") / "historical_identity_corrections_2016_2025.json")
WLP_SOURCES = list(ticker_corrections.WLP_SOURCES)


def correct_symbols(symbols: set[str], as_of: str) -> tuple[set[str], list[dict]]:
    return ticker_corrections.correct_symbols(symbols, as_of, start=WLP_START, end=WLP_END, source_urls=WLP_SOURCES)


@cache
def identity_nominations() -> tuple[dict, ...]:
    """Reviewed label -> CIK nominations; SEC evidence must still confirm them."""
    rows = [row for path in NOMINATION_PATHS for row in json.loads(path.read_text(encoding="utf-8"))["entries"]]
    return ticker_corrections.parse_nominations(rows)


def apply_nominations(by_symbol: dict[str, list[dict]]) -> dict[str, list[dict]]:
    return ticker_corrections.apply_nominations(by_symbol, identity_nominations())
