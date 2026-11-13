"""Data gate of ``NSI-v1`` (#252): net share issuance coverage and restatement audit, without returns.

The reserve candidate of ``docs/research/268-mapa-hipotesis.md`` (section 5) may
only go on if, at every signal (first NYSE session of July, 2011–2025, inside the
observed period):

- at least 70 % of the S&P 500 members have both share figures in one 10-K
  (members without an accepted historical identity count as missing), and
- at least 90 % of the issuer-dates with a previous 10-K reconcile with it, as
  equal or restated by a simple split ratio.

Otherwise it closes as unfeasible. Members, identity and the download are the
same as the CbOP gate's (:mod:`cbop_coverage`), with share tags in their own store.
"""

from collections.abc import Callable
from datetime import date

from gabi.application.research.reservations import require_observed_period
from gabi.domain.research import net_issuance

TAGS: dict[str, tuple[str, ...]] = {"shares": net_issuance.SHARE_TAGS}


def audit(members: dict[date, dict[str, str | None]], *, facts: Callable[[str], dict],
          progress: Callable[[int, int], None] = lambda done, total: None) -> dict:
    if not members:
        raise ValueError("Indica al menos una fecha de señal.")
    signals = sorted(members)
    require_observed_period(signals[0].isoformat(), signals[-1].isoformat())
    years, examples = [], {}
    for done, signal in enumerate(signals, 1):
        rows: list[dict] = []
        for symbol, cik in sorted(members[signal].items()):
            if cik is None:
                rows.append({"symbol": symbol, "state": "absent", "reason": "identity_unresolved",
                             "check": "no_previous_filing"})
                continue
            value = net_issuance.issuance(facts(cik), signal)
            rows.append({"symbol": symbol, "state": value.state, "reason": value.reason, "check": value.check})
        years.append({"signal": signal.isoformat(), **net_issuance.coverage(rows)})
        examples[signal.isoformat()] = {
            "missing": sorted(f"{row['symbol']}:{row['reason']}" for row in rows if row["state"] != "computed")[:40],
            "mismatch": sorted(row["symbol"] for row in rows if row["check"] == "mismatch")[:40]}
        progress(done, len(signals))
    failed = [year["signal"] for year in years if not year["passes"]]
    return {"version": net_issuance.VERSION, "coverage_threshold": net_issuance.COVERAGE_THRESHOLD,
            "reconciled_threshold": net_issuance.RECONCILED_THRESHOLD, "signals": years, "examples": examples,
            "passes": not failed, "failed_signals": failed,
            "decision": "continue_to_exploratory" if not failed else "close_unfeasible", "returns_read": False}
