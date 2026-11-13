"""Prospective record of GABI-ENS-VQE-v1 (#237): calendar, record and hash chain, without returns.

The rules come from ``docs/ensemble-robustness/preregistro.json`` (``prospective_plan``) and the
decisions approved in #237. A quarter may be recorded from its signal date up to five sessions
later. A quarter whose window closed unrecorded is published as not recorded, never filled in.
Scores reuse the #53 block, aggregation and selection rules unchanged; no return enters here.
"""

from collections.abc import Sequence
from datetime import date

import pandas as pd

from gabi.domain.research.ensemble_robustness import (
    BLOCKS,
    SIGNALS,
    check_published_blocks,
    fingerprint,
    json_ready,
    metric_columns,
    select,
    signals,
    universe,
)

MODEL = "GABI-ENS-VQE-v1"
SPEC_SHA256 = "8609a0770a49d00c72bf5bb507d55551eba88b895543b305ca66715292555bca"
FIRST_SIGNAL = date(2026, 12, 21)
SIGNAL_MONTHS = (3, 6, 9, 12)
SIGNAL_DAY = 21
WINDOW_SESSIONS = 5
STATUSES = ("recorded", "not_recorded")


def signal_dates(until: date) -> list[date]:
    """#43's calendar from the first prospective signal: the 21st of March, June, September, December."""
    result: list[date] = []
    year, index = FIRST_SIGNAL.year, SIGNAL_MONTHS.index(FIRST_SIGNAL.month)
    while True:
        day = date(year, SIGNAL_MONTHS[index], SIGNAL_DAY)
        if day > until:
            return result
        result.append(day)
        index = (index + 1) % len(SIGNAL_MONTHS)
        year += index == 0


def window_end(signal: date, sessions: Sequence[date]) -> date:
    """Last day a quarter may be recorded: the fifth session after the first session on or after the signal."""
    following = sorted(day for day in sessions if day >= signal)
    if len(following) <= WINDOW_SESSIONS:
        raise ValueError("El calendario de sesiones no cubre la ventana de registro.")
    return following[WINDOW_SESSIONS]


def open_signal(today: date, sessions: Sequence[date]) -> date | None:
    """The signal whose recording window contains ``today``, if any."""
    for signal in reversed(signal_dates(today)):
        if today <= window_end(signal, sessions):
            return signal
    return None


def missed(today: date, recorded: set[date], sessions: Sequence[date]) -> list[date]:
    """Signals whose window closed before ``today`` without a record."""
    return [signal for signal in signal_dates(today)
            if signal not in recorded and window_end(signal, sessions) < today]


def _seal(body: dict) -> dict:
    body = json_ready(body)
    return {**body, "sha256": fingerprint(body)}


def not_recorded(signal: date, end: date, previous: str | None) -> dict:
    return _seal({"model": MODEL, "spec_sha256": SPEC_SHA256, "status": "not_recorded",
                  "signal_date": signal.isoformat(), "window_end": end.isoformat(), "previous_sha256": previous})


def record(signal: date, recorded_on: date, scored: pd.DataFrame, spec: dict, *, previous: str | None,
           excluded: dict[str, str], entry: dict[str, dict], evidence: list[dict], inputs: dict) -> dict:
    """One quarter: complete U_t scores, the four Top-20 and their entry prices, sealed into the chain.

    ``scored`` is indexed by symbol with ``entity_id``, ``division``, the metric percentiles and the
    blocks of the frozen #60 scorer; the blocks are recomputed before anything else (#53)."""
    frame = scored.rename_axis("symbol").reset_index()
    check_published_blocks(frame, spec)
    members = universe(frame)
    table = signals(members, spec)
    portfolios = {}
    for name in SIGNALS:
        chosen, cash = select(table[name], members, spec)
        portfolios[name] = {"symbols": chosen, "cash_slots": cash}
    columns = ["symbol", "entity_id", "division", *metric_columns(spec), *BLOCKS]
    rows = [{**row, "ENS": ens, **entry.get(row["symbol"], {"date": None, "close": None, "adj_close": None})}
            for row, ens in zip(members[columns].to_dict("records"), table["ENS"], strict=True)]
    minimum = spec["universe"]["minimum_size"]
    return _seal({
        "model": MODEL, "spec_sha256": SPEC_SHA256, "status": "recorded",
        "signal_date": signal.isoformat(), "recorded_on": recorded_on.isoformat(), "previous_sha256": previous,
        "universe": {"size": len(members), "minimum_size": minimum, "evaluable": len(members) >= minimum,
                     "scored": len(frame), "excluded": [{"symbol": symbol, "reason": reason}
                                                        for symbol, reason in sorted(excluded.items())]},
        "scores": rows, "portfolios": portfolios, "sic_evidence": evidence, "inputs": inputs,
    })


def verify_chain(records: Sequence[dict]) -> dict:
    """Integrity, coverage and continuity only, as the preregistration allows before each look."""
    previous: str | None = None
    expected = signal_dates(date.fromisoformat(records[-1]["signal_date"])) if records else []
    if [row["signal_date"] for row in records] != [day.isoformat() for day in expected]:
        raise ValueError("El registro prospectivo no sigue el calendario sin huecos.")
    for row in records:
        body = {key: value for key, value in row.items() if key != "sha256"}
        if row.get("sha256") != fingerprint(body):
            raise ValueError(f"Huella alterada en {row.get('signal_date')}.")
        if row["model"] != MODEL or row["spec_sha256"] != SPEC_SHA256 or row["status"] not in STATUSES:
            raise ValueError(f"Modelo o especificación distintos en {row['signal_date']}.")
        if row["previous_sha256"] != previous:
            raise ValueError(f"Cadena rota en {row['signal_date']}.")
        previous = row["sha256"]
    recorded = [row for row in records if row["status"] == "recorded"]
    return {"records": len(records), "recorded": len(recorded), "not_recorded": len(records) - len(recorded),
            "last_signal": records[-1]["signal_date"] if records else None, "last_sha256": previous,
            "below_minimum": [row["signal_date"] for row in recorded if not row["universe"]["evaluable"]]}
