"""Data gate of ``CBOP-v1`` (#252): CbOP coverage of the S&P 500 at each signal, without returns.

Phase 1 of the preregistration proposed in ``docs/research/268-mapa-hipotesis.md``:
before any return is computed, the eligible universe (members at the signal,
financials excluded) must have a computed CbOP for at least 70 % of its issuers
in every year; otherwise the hypothesis closes as unfeasible. The audit reads
the composition, the issuers' SIC codes and their SEC facts filed before each
signal; it reads no prices and only dates inside the observed period.
"""

from collections.abc import Callable
from datetime import date

from gabi.application.research.reservations import require_observed_period
from gabi.domain.research import cbop

SIGNAL_MONTH = 7  # The first session of July, after the 10-K season.


def audit(signals: list[date], *, membership: Callable[[str], dict], facts: Callable[[str, date], dict],
          sic: Callable[[str, date], int | None], threshold: float = cbop.COVERAGE_THRESHOLD,
          progress: Callable[[int, int], None] = lambda done, total: None) -> dict:
    """``facts(symbol, signal)`` returns the symbol's issuer facts known at the signal (``companyfacts`` shape)."""
    if not signals:
        raise ValueError("Indica al menos una fecha de señal.")
    signals = sorted(signals)
    require_observed_period(signals[0].isoformat(), signals[-1].isoformat())
    years, examples = [], {}
    for done, signal in enumerate(signals, 1):
        members = membership(signal.isoformat())
        rows = []
        for symbol in members["symbols"]:
            code = sic(symbol, signal)
            value = cbop.cbop(facts(symbol, signal), signal, sic=code)
            rows.append({"symbol": symbol, "state": value.metric.state, "reason": value.metric.reason,
                         "imputed": list(value.imputed), "sic": code})
        summary = cbop.coverage(rows, threshold=threshold)
        years.append({"signal": signal.isoformat(), "membership_exact": members.get("is_exact"),
                      "unknown_sic": sum(row["sic"] is None for row in rows), **summary})
        examples[signal.isoformat()] = sorted(row["symbol"] for row in rows
                                              if row["state"] not in {"computed", "not_applicable"})[:25]
        progress(done, len(signals))
    failed = [year["signal"] for year in years if not year["passes"]]
    return {"version": cbop.VERSION, "threshold": threshold, "signals": years, "missing_examples": examples,
            "passes": not failed, "failed_signals": failed,
            "decision": "continue_to_exploratory" if not failed else "close_unfeasible",
            "returns_read": False}
