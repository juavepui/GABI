"""Compatibility facade for the Streamlit portfolio page."""

from gabi.domain.portfolio.selection import (
    MIN_COVERAGE,
    allocate_new_capital,
    eligible_candidates,
    parse_holdings,
    target_portfolio,
)

__all__ = ["MIN_COVERAGE", "eligible_candidates", "target_portfolio", "parse_holdings", "allocate_new_capital"]
