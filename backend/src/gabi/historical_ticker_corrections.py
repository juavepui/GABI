"""Small ledger of independently reviewed historical ticker labels.

Community snapshots may apply a later ticker retrospectively. Corrections are
date-bounded, source-attributed and applied at query time; raw files stay intact.
"""

from gabi.domain.research import ticker_corrections
from gabi.domain.research.ticker_corrections import WLP_END as WLP_END
from gabi.domain.research.ticker_corrections import WLP_START as WLP_START
from gabi.infrastructure.storage import reviewed_resources

# #34: same ledger format for 2016-2025; entries are date-bounded, so both load together.
NOMINATION_PATHS = reviewed_resources.NOMINATION_PATHS
NOMINATIONS_PATH = NOMINATION_PATHS[0]
WLP_SOURCES = list(ticker_corrections.WLP_SOURCES)


def correct_symbols(symbols: set[str], as_of: str) -> tuple[set[str], list[dict]]:
    return ticker_corrections.correct_symbols(symbols, as_of, start=WLP_START, end=WLP_END, source_urls=WLP_SOURCES)


identity_nominations = reviewed_resources.identity_nominations


def apply_nominations(by_symbol: dict[str, list[dict]]) -> dict[str, list[dict]]:
    return ticker_corrections.apply_nominations(by_symbol, identity_nominations())
