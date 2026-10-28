"""Explicit prospective recording of GABI-ENS-VQE-v1 (#237); verification reads only the chain.

Data refresh is a separate explicit action: this use case reads what is stored, adds the SEC
submissions it needs for the dated SIC, and writes one sealed record. It never reads a return.
"""

from collections.abc import Callable
from datetime import date, timedelta
from typing import Protocol

import pandas as pd

from gabi.domain.research import ensemble_prospective as rules
from gabi.domain.research.ensemble_robustness import fingerprint

ELIGIBLE_COVERAGE = .70  # GABI filter: non-empty Composite and >= 70 % coverage, as #48/#60


class LiveSources(Protocol):
    def sessions(self, start: date, end: date) -> list[date]: ...
    def constituents(self) -> tuple[list[str], dict]: ...
    def ranking(self, signal: date, symbols: list[str]) -> pd.DataFrame: ...
    def divisions(self, frame: pd.DataFrame, signal: date) -> pd.DataFrame: ...
    def score(self, frame: pd.DataFrame) -> pd.DataFrame: ...
    def entry_prices(self, symbols: list[str], signal: date) -> dict[str, dict]: ...


class RecordStore(Protocol):
    def all(self) -> list[dict]: ...
    def write(self, record: dict) -> str: ...


def verify(store: RecordStore) -> dict:
    return rules.verify_chain(store.all())


def record_due(today: date, *, spec: dict, sources: LiveSources, store: RecordStore,
               inputs: Callable[[], dict]) -> dict:
    """Record the open quarter once; first seal every quarter whose window closed unrecorded."""
    if fingerprint(spec) != rules.SPEC_SHA256:
        raise ValueError("La especificación sellada de #53 ha cambiado; el registro de v1 termina.")
    if today < rules.FIRST_SIGNAL:
        raise ValueError(f"El registro prospectivo empieza el {rules.FIRST_SIGNAL.isoformat()}.")
    existing = store.all()
    chain = rules.verify_chain(existing)
    sessions = sources.sessions(rules.FIRST_SIGNAL - timedelta(days=7), today + timedelta(days=21))
    done = {date.fromisoformat(row["signal_date"]) for row in existing}
    previous, written = chain["last_sha256"], []
    for closed in rules.missed(today, done, sessions):
        marker = rules.not_recorded(closed, rules.window_end(closed, sessions), previous)
        written.append(store.write(marker))
        previous = marker["sha256"]
    signal = rules.open_signal(today, sessions)
    if signal is None or signal in done:
        return {"recorded": None, "not_recorded": written,
                "reason": "ya registrado" if signal else "ninguna ventana de registro abierta"}

    prior = max(day for day in sessions if day < signal)
    spy = sources.entry_prices(["SPY"], signal).get("SPY") or {}
    if not spy.get("date") or date.fromisoformat(spy["date"]) < prior:
        raise ValueError(f"Precios sin actualizar: hacen falta cierres del {prior.isoformat()} o posteriores.")

    symbols, membership = sources.constituents()
    ranking = sources.ranking(signal, symbols)
    eligible = ranking.loc[ranking["composite_score"].notna() & (ranking["score_coverage"] >= ELIGIBLE_COVERAGE)]
    labels = sources.divisions(eligible, signal)
    classified = labels.index[labels["division"].astype(str) != ""]
    # The retrospective universe was fully classified; live issuers without a valid dated SIC
    # are left out of U_t and published with their reason, never dropped silently.
    excluded = {str(symbol): str(labels.at[symbol, "reason"]) for symbol in labels.index.difference(classified)}
    frame = eligible.loc[classified].assign(division=labels.loc[classified, "division"])
    scored = sources.score(frame)
    members = [str(symbol) for symbol in scored.index]
    evidence = labels.reset_index().to_dict("records")
    sealed = rules.record(signal, today, scored, spec, previous=previous, excluded=excluded,
                          entry=sources.entry_prices(members, signal), evidence=evidence,
                          inputs={**inputs(), "membership": membership, "constituents": len(symbols),
                                  "ranked": len(ranking), "eligible": len(eligible)})
    written.append(store.write(sealed))
    return {"recorded": sealed["signal_date"], "not_recorded": written[:-1], "path": written[-1],
            "universe": sealed["universe"]["size"], "evaluable": sealed["universe"]["evaluable"],
            "excluded": len(excluded), "sha256": sealed["sha256"]}
