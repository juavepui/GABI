"""Compatibility classification and paced retry shared with existing sources."""

from gabi.domain.market.source_errors import classify
from gabi.domain.market.sync_events import fingerprint as fingerprint
from gabi.sync_state import retry as retry


def fred_error(exc: Exception) -> str:
    return classify(str(exc), "FRED")[1]


def sec_error(exc: Exception) -> str:
    return classify(str(exc), "SEC EDGAR")[1]
