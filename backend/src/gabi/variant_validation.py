"""Compatibility entry point for the published R3 validation harness."""

from collections.abc import Callable, Mapping

from gabi import portfolio_backtest
from gabi.application.research.variant_validation import run_validation as _run_validation
from gabi.domain.research.variant_validation import (
    DEFAULT_END as DEFAULT_END,
)
from gabi.domain.research.variant_validation import (
    DEFAULT_START as DEFAULT_START,
)
from gabi.domain.research.variant_validation import (
    DEFAULT_WINDOWS as DEFAULT_WINDOWS,
)
from gabi.domain.research.variant_validation import (
    VariantSpec as VariantSpec,
)
from gabi.domain.research.variant_validation import expected_rebalance_dates, window_metrics


def _expected_rebalance_dates(start: str, end: str, months: int) -> list[str]:
    return expected_rebalance_dates(start, end, months)


def _window_metrics(result: dict, start: str, end: str) -> dict:
    return window_metrics(result, start, end)


def run_validation(variants: list[VariantSpec], *, start: str = DEFAULT_START,
                   end: str = DEFAULT_END, top_n: int = 20,
                   windows: Mapping[str, tuple[str, str]] = DEFAULT_WINDOWS,
                   runner: Callable[..., dict] = portfolio_backtest.run) -> dict:
    return _run_validation(variants, start=start, end=end, top_n=top_n,
                           windows=windows, runner=runner)
