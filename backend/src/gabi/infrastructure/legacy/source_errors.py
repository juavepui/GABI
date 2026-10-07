"""Compatibility classification and paced retry shared with existing sources."""

from gabi.data_fetch import _classify_error
from gabi.sync_state import retry as retry


def fred_error(exc: Exception) -> str:
    return _classify_error(exc, service="FRED")[1]
