"""History of published ideas (#247): additive events, their state and their evaluation against the S&P 500.

Version ``ideas-v1``. A published investment card (#246) becomes an idea. What
happens to it afterwards is appended, never edited: ``publicada`` (once, when the
card is published), ``revisada``, ``retirada``, ``cerrada`` and ``corregida`` (which
points at an earlier event and states the correction). Each event carries the
SHA-256 of the previous one, so the chain shows any rewrite.

- Retired, closed, losing and never executed ideas stay in the history and are
  evaluated like the rest: judging only winners or only closed theses would bias it.
- An idea is evaluated from the day it was recorded as published, never from an
  earlier date: nothing is registered retrospectively as prospective.
- After ``retirada`` or ``cerrada`` only corrections are accepted.

Nothing here reads market data; prices come in as already aligned series.
"""

import hashlib
import json
import math

import pandas as pd

VERSION = "ideas-v1"
KINDS = ("publicada", "revisada", "retirada", "cerrada", "corregida")
FINAL = ("retirada", "cerrada")
OUTCOMES = ("acertada", "parcial", "fallida")
MAX_TEXT = 2000


class IdeaError(ValueError):
    """An event that cannot be appended; the message is for the investor."""


def _text(value, field: str, *, required: bool = False) -> str:
    text = str(value or "").strip()
    if required and not text:
        raise IdeaError(f"Indica {field}.")
    if len(text) > MAX_TEXT:
        raise IdeaError(f"«{field}» supera {MAX_TEXT} caracteres.")
    return text


def payload(kind: str, raw: dict, events: list[dict]) -> dict:
    """The validated payload of a new event, given the idea's previous events."""
    if kind not in KINDS:
        raise IdeaError("Tipo de evento no válido.")
    if kind == "publicada":
        if events:
            raise IdeaError("La idea ya está publicada.")
        return {"card_id": int(raw["card_id"]), "symbol": str(raw["symbol"]),
                "snapshot_sha256": raw.get("snapshot_sha256"), "review_due": raw.get("review_due"),
                "position_eur": raw.get("position_eur"), "round_trip_share": raw.get("round_trip_share")}
    if not events:
        raise IdeaError("Solo una ficha publicada se convierte en idea.")
    final = state(events)["status"] in FINAL
    if kind == "corregida":
        target = raw.get("corrects")
        if not isinstance(target, int) or target not in {event["sequence"] for event in events}:
            raise IdeaError("Indica qué evento se corrige.")
        return {"corrects": target, "text": _text(raw.get("text"), "la corrección", required=True)}
    if final:
        raise IdeaError("La idea ya está cerrada o retirada: solo admite correcciones.")
    if kind == "revisada":
        return {"text": _text(raw.get("text"), "la revisión", required=True)}
    if kind == "retirada":
        return {"reason": _text(raw.get("reason"), "por qué se retira", required=True)}
    outcome = raw.get("outcome")
    if outcome not in OUTCOMES:
        raise IdeaError("El cierre indica si la tesis fue acertada, parcial o fallida.")
    return {"outcome": outcome, "cause": _text(raw.get("cause"), "la causa", required=True),
            "executed": bool(raw.get("executed"))}


def digest(event: dict) -> str:
    body = {key: event[key] for key in ("idea_id", "sequence", "kind", "recorded_at", "payload", "previous_sha256")}
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                                     default=str).encode("utf-8")).hexdigest()


def chain(idea_id: int, events: list[dict], kind: str, body: dict, recorded_at: str) -> dict:
    """The next event, linked to the last one."""
    event = {"idea_id": idea_id, "sequence": len(events) + 1, "kind": kind, "recorded_at": recorded_at,
             "payload": body, "previous_sha256": events[-1]["sha256"] if events else None}
    return event | {"sha256": digest(event)}


def verify(events: list[dict]) -> bool:
    previous = None
    for index, event in enumerate(events, 1):
        if event["sequence"] != index or event["previous_sha256"] != previous or event["sha256"] != digest(event):
            return False
        previous = event["sha256"]
    return True


def state(events: list[dict]) -> dict:
    """Status, dates and outcome of an idea from its events."""
    published = events[0]
    status, ended, outcome = "abierta", None, None
    for event in events[1:]:
        if event["kind"] in FINAL:
            status, ended = event["kind"], event["recorded_at"][:10]
            outcome = event["payload"] if event["kind"] == "cerrada" else None
    return {"status": status, "published_on": published["recorded_at"][:10], "ended_on": ended,
            "outcome": outcome, "reviews": sum(event["kind"] == "revisada" for event in events),
            "corrections": sum(event["kind"] == "corregida" for event in events)}


def evaluate(stock_eur: pd.Series, index_eur: pd.Series, *, round_trip_share: float | None) -> dict:
    """Total return net of the card's round-trip costs, drawdown and excess over the index, both in euros.

    Both series are total-return prices in euros on the same sessions, from the
    publication to the end (close, withdrawal or today)."""
    joined = pd.concat([stock_eur.rename("stock"), index_eur.rename("index")], axis=1).dropna()
    if len(joined) < 2 or (joined <= 0).any().any():
        return {"status": "insufficient_prices", "sessions": len(joined)}
    stock, index = joined["stock"], joined["index"]
    gross = float(stock.iloc[-1] / stock.iloc[0] - 1)
    cost = round_trip_share or 0.0
    net = (1 + gross) * (1 - cost) - 1
    benchmark = float(index.iloc[-1] / index.iloc[0] - 1)
    drawdown = float((stock / stock.cummax() - 1).min())
    return {"status": "ok", "start": joined.index[0].date().isoformat(), "end": joined.index[-1].date().isoformat(),
            "days": (joined.index[-1] - joined.index[0]).days, "sessions": len(joined),
            "return_net": net, "costs_included": round_trip_share is not None, "index_return": benchmark,
            "excess": net - benchmark, "max_drawdown": drawdown,
            "index_max_drawdown": float((index / index.cummax() - 1).min())}


def summary(rows: list[dict]) -> dict:
    """Every idea counts, whatever its status: hit rate over closed ones, excess over all evaluated ones."""
    evaluated = [row for row in rows if (row.get("evaluation") or {}).get("status") == "ok"]
    closed = [row for row in rows if row["state"]["status"] == "cerrada"]
    excess = [row["evaluation"]["excess"] for row in evaluated]
    beat = sum(value > 0 for value in excess)
    return {"ideas": len(rows), "open": sum(row["state"]["status"] == "abierta" for row in rows),
            "closed": len(closed), "retired": sum(row["state"]["status"] == "retirada" for row in rows),
            "evaluated": len(evaluated), "beat_index": beat,
            "median_excess": float(pd.Series(excess).median()) if excess else None,
            "mean_excess": float(sum(excess) / len(excess)) if excess else None,
            "thesis_hits": {outcome: sum((row["state"]["outcome"] or {}).get("outcome") == outcome for row in closed)
                            for outcome in OUTCOMES},
            "note": "Cuentan todas las ideas publicadas: abiertas, cerradas, retiradas, ganadoras y perdedoras."}


def finite(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None
