"""Data gate of ``CBOP-v1`` (#252): CbOP coverage of the S&P 500 at each signal, without returns.

Phase 1 of the preregistration proposed in ``docs/research/268-mapa-hipotesis.md``:
before any return is computed, the eligible universe (members at the signal,
financials excluded) must have a computed CbOP for at least 70 % of its issuers
in every year; otherwise the hypothesis closes as unfeasible.

Members are mapped to their issuer (CIK) with the accredited historical identity
intervals, so issuers that later left the index count as much as survivors; a
member without an accepted identity is eligible and missing. The download is an
explicit, resumable step; the audit reads the composition, the stored facts filed
before each signal and each issuer's SIC. Neither reads prices, and only dates
inside the observed period are accepted.
"""

import hashlib
import json
from collections.abc import Callable, Iterable
from datetime import date

from gabi.application.research.reservations import require_observed_period
from gabi.domain.market.sec_facts import _extract_raw_facts
from gabi.domain.research import cbop

ACCEPTED_IDENTITY = frozenset({"confirmed_by_multiple_evidence", "confirmed_historical_ticker",
                               "corroborated_candidate"})


def cik_at(intervals: Iterable[dict], symbol: str, day: date) -> str | None:
    """The single accepted CIK of ``symbol`` on ``day``; ``None`` if absent, unresolved or ambiguous."""
    text = day.isoformat()
    found = {row["cik"] for row in intervals if row["symbol"] == symbol
             and row["valid_from"] <= text < row["valid_to"] and row["status"] in ACCEPTED_IDENTITY}
    return found.pop() if len(found) == 1 else None


def issuers(signals: list[date], membership: Callable[[str], dict], intervals: list[dict]) -> dict:
    """``{signal: {symbol: cik | None}}`` for the members at each signal."""
    if not signals:
        raise ValueError("Indica al menos una fecha de señal.")
    require_observed_period(min(signals).isoformat(), max(signals).isoformat())
    by_symbol: dict[str, list[dict]] = {}
    for row in intervals:
        by_symbol.setdefault(row["symbol"], []).append(row)
    return {signal: {symbol: cik_at(by_symbol.get(symbol, []), symbol, signal)
                     for symbol in membership(signal.isoformat())["symbols"]} for signal in sorted(signals)}


def _sha256(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


CBOP_TAGS: dict[str, tuple[str, ...]] = {"USD": cbop.USD_TAGS}


def tags_sha256(tags: dict[str, tuple[str, ...]] | None = None) -> str:
    """Fingerprint of the stored tag set: a download made with another set is fetched again.

    The CbOP set keeps its original fingerprint (a list of its USD tags)."""
    if tags is None or tags == CBOP_TAGS:
        return _sha256(list(cbop.USD_TAGS))
    return _sha256({unit: list(names) for unit, names in sorted(tags.items())})


def download(ciks: Iterable[str], *, done: set[str], companyfacts: Callable[[str], dict],
             submissions: Callable[[str], dict], save: Callable[..., None], now: Callable[[], str],
             progress: Callable[[int, int], None] = lambda done, total: None,
             tags: dict[str, tuple[str, ...]] | None = None) -> dict:
    """Downloads each CIK not in ``done`` (those stored with the current tags); no XBRL is stored as ``absent``.

    Only ``tags`` (unit → tag names; the CbOP ones by default) are kept. Transient failures propagate after the caller's
    retries; what was saved stays, so a new run resumes."""
    wanted = tags or CBOP_TAGS
    fingerprint = tags_sha256(wanted)
    pending = sorted(set(ciks) - done)
    counts = {"pending": len(pending), "ok": 0, "absent": 0}
    for index, cik in enumerate(pending, 1):
        filings = submissions(cik)
        code = str(filings.get("sic") or "").strip()
        sic = int(code) if code.isdigit() else None
        try:
            facts = companyfacts(cik)
        except ValueError as exc:  # SEC answers 404: no structured data for this issuer.
            save(cik, rows=[], sic=sic, status="absent", reason=str(exc), fetched_at=now(), facts_sha256=None,
                 submissions_sha256=_sha256(filings), tags_sha256=fingerprint)
            counts["absent"] += 1
        else:
            rows = [row for unit, names in wanted.items() for row in _extract_raw_facts(facts, list(names), unit=unit)]
            save(cik, rows=rows, sic=sic, status="ok", reason=None, fetched_at=now(), facts_sha256=_sha256(facts),
                 submissions_sha256=_sha256(filings), tags_sha256=fingerprint)
            counts["ok"] += 1
        progress(index, len(pending))
    return counts


def audit(members: dict[date, dict[str, str | None]], *, facts: Callable[[str], dict],
          sic: Callable[[str], int | None], threshold: float = cbop.COVERAGE_THRESHOLD,
          progress: Callable[[int, int], None] = lambda done, total: None) -> dict:
    """``members`` comes from :func:`issuers`; ``facts(cik)`` holds every stored fact, filtered here by signal."""
    if not members:
        raise ValueError("Indica al menos una fecha de señal.")
    signals = sorted(members)
    require_observed_period(signals[0].isoformat(), signals[-1].isoformat())
    years, examples = [], {}
    for done, signal in enumerate(signals, 1):
        rows: list[dict] = []
        for symbol, cik in sorted(members[signal].items()):
            if cik is None:
                rows.append({"symbol": symbol, "state": "absent", "reason": "identity_unresolved", "imputed": [],
                             "sic": None})
                continue
            code = sic(cik)
            value = cbop.cbop(facts(cik), signal, sic=code)
            rows.append({"symbol": symbol, "state": value.metric.state, "reason": value.metric.reason,
                         "imputed": list(value.imputed), "sic": code})
        summary = cbop.coverage(rows, threshold=threshold)
        years.append({"signal": signal.isoformat(), "unknown_sic": sum(row["sic"] is None for row in rows),
                      **summary})
        examples[signal.isoformat()] = sorted(f"{row['symbol']}:{row['reason']}" for row in rows
                                              if row["state"] not in {"computed", "not_applicable"})[:40]
        progress(done, len(signals))
    failed = [year["signal"] for year in years if not year["passes"]]
    return {"version": cbop.VERSION, "data_amendment": cbop.DATA_AMENDMENT, "threshold": threshold, "signals": years, "missing_examples": examples,
            "passes": not failed, "failed_signals": failed,
            "decision": "continue_to_exploratory" if not failed else "close_unfeasible",
            "returns_read": False}
