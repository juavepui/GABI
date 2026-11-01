"""History of published ideas (#247): additive events, private notes and evaluation against the S&P 500 in EUR.

A card's publication records its idea (idempotent: one ``publicada`` per card) and
discarding a published card retires it. Reads use only the local price cache
(adjusted closes, SPY and USDEUR=X); a missing series makes the evaluation
``insufficient_prices``, never an estimate.
"""

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Protocol

import pandas as pd

from gabi.application.errors import QueryError
from gabi.domain.portfolio import idea_alerts
from gabi.domain.portfolio import ideas as rules

INDEX, FX = "SPY", "USDEUR=X"
Rows = list[dict]  # Named outside the class, whose ``list`` method would shadow the builtin.
History = dict[int, list[dict]]
MAX_IDEAS = 200


class IdeaStore(Protocol):
    def ideas(self, limit: int) -> list[int]: ...
    def events(self, idea_id: int) -> list[dict]: ...
    def append(self, event: dict) -> bool: ...
    def notes(self, idea_id: int) -> list[dict]: ...
    def observations(self, idea_id: int) -> dict[int, list[dict]]: ...
    def record(self, idea_id: int, observations: list[dict], alerts: list[dict], now: str) -> int: ...
    def alerts(self, idea_id: int) -> list[dict]: ...
    def add_note(self, idea_id: int, text: str, now: str) -> int: ...
    def save_note(self, note_id: int, text: str, now: str) -> bool: ...
    def delete_note(self, note_id: int) -> bool: ...


def _adjusted(frame: pd.DataFrame | None) -> pd.Series:
    if frame is None or frame.empty:
        return pd.Series(dtype=float)
    column = "adj_close" if "adj_close" in frame and frame["adj_close"].notna().any() else "close"
    series = frame[column].dropna().astype(float)
    series.index = pd.to_datetime(series.index)
    return series[series > 0]


class Ideas:
    def __init__(self, store: IdeaStore, prices: Callable[[list[str], str], dict[str, pd.DataFrame]],
                 today: Callable[[], date] = date.today, now: Callable[[], datetime] = lambda: datetime.now(UTC)):
        """``prices(symbols, start)`` reads cached daily prices; it never downloads."""
        self.store, self.prices, self.today, self.now = store, prices, today, now

    def _stamp(self) -> str:
        return self.now().isoformat(timespec="seconds")

    def _append(self, idea_id: int, kind: str, raw: dict) -> dict:
        events = self.store.events(idea_id)
        try:
            body = rules.payload(kind, raw, events)
        except rules.IdeaError as exc:
            raise QueryError("invalid_idea_event", str(exc), 422) from exc
        event = rules.chain(idea_id, events, kind, body, self._stamp())
        if not self.store.append(event):
            raise QueryError("idea_conflict", "Otra operación modificó la idea; vuelve a intentarlo.", 409)
        return event

    def record_publication(self, card: dict) -> None:
        """Called when a card is published; a second call for the same card does nothing."""
        if self.store.events(card["id"]):
            return
        decision = (card.get("snapshot") or {}).get("decision") or {}
        self._append(card["id"], "publicada", {
            "card_id": card["id"], "symbol": card["symbol"], "snapshot_sha256": card.get("snapshot_sha256"),
            "review_due": card["content"].get("review_due"), "position_eur": card["content"].get("position_eur"),
            "round_trip_share": (decision.get("costs") or {}).get("round_trip_share")})

    def record_withdrawal(self, card: dict, reason: str) -> None:
        """A published card that is discarded retires its idea, which stays in the history."""
        events = self.store.events(card["id"])
        if events and rules.state(events)["status"] == "abierta":
            self._append(card["id"], "retirada", {"reason": reason})

    def append(self, idea_id: int, kind: str, raw: dict) -> dict:
        if kind == "publicada":
            raise QueryError("invalid_idea_event", "La publicación la registra la ficha.", 422)
        if not self.store.events(idea_id):
            raise QueryError("idea_not_found", "No existe esa idea.", 404)
        self._append(idea_id, kind, raw)
        return self.detail(idea_id)

    def _evaluate(self, events: list[dict], status: dict) -> dict:
        symbol = events[0]["payload"]["symbol"]
        start = date.fromisoformat(status["published_on"])
        end = date.fromisoformat(status["ended_on"]) if status["ended_on"] else self.today()
        try:
            frames = self.prices([symbol, INDEX, FX], (start - timedelta(days=10)).isoformat())
        except QueryError:
            frames = {}
        rate = _adjusted(frames.get(FX))
        window = pd.date_range(pd.Timestamp(start), pd.Timestamp(end), freq="D")

        def euros(name: str) -> pd.Series:
            prices = _adjusted(frames.get(name))
            prices = prices[(prices.index >= pd.Timestamp(start)) & (prices.index <= pd.Timestamp(end))]
            fx = rate.reindex(rate.index.union(window)).ffill().reindex(prices.index)
            return (prices * fx).dropna()

        missing = [name for name in (symbol, INDEX, FX) if _adjusted(frames.get(name)).empty]
        if missing:
            return {"status": "insufficient_prices", "missing": missing}
        return rules.evaluate(euros(symbol), euros(INDEX), round_trip_share=events[0]["payload"].get("round_trip_share"))

    def _row(self, idea_id: int, events: list[dict]) -> dict:
        status = rules.state(events)
        alerts = self.store.alerts(idea_id)
        return {"pending_alerts": idea_alerts.pending(alerts, events), "idea_id": idea_id, "symbol": events[0]["payload"]["symbol"], "card_id": events[0]["payload"]["card_id"],
                "review_due": events[0]["payload"].get("review_due"), "state": status,
                "evaluation": self._evaluate(events, status), "chain_ok": rules.verify(events)}

    def list(self, limit: int = MAX_IDEAS) -> dict:
        rows = [self._row(idea_id, self.store.events(idea_id)) for idea_id in self.store.ideas(min(limit, MAX_IDEAS))]
        return {"version": rules.VERSION, "as_of": self.today().isoformat(), "items": rows,
                "summary": rules.summary(rows),
                "benchmark": "S&P 500 (SPY, cierre ajustado) en EUR con USDEUR=X, mismas fechas que cada idea"}

    def detail(self, idea_id: int) -> dict:
        events = self.store.events(idea_id)
        if not events:
            raise QueryError("idea_not_found", "No existe esa idea.", 404)
        return self._row(idea_id, events) | {"events": events, "notes": self.store.notes(idea_id),
                                             "alerts": self.store.alerts(idea_id)}

    def observations(self, idea_id: int) -> History:
        return self.store.observations(idea_id)

    def record_alerts(self, idea_id: int, observations: Rows, alerts: Rows) -> int:
        """Stores the alert job's new observations and alerts; returns how many alerts were new."""
        return self.store.record(idea_id, observations, alerts, self._stamp())

    def add_note(self, idea_id: int, text: str) -> dict:
        if not self.store.events(idea_id):
            raise QueryError("idea_not_found", "No existe esa idea.", 404)
        self.store.add_note(idea_id, self._note(text), self._stamp())
        return self.detail(idea_id)

    def save_note(self, idea_id: int, note_id: int, text: str) -> dict:
        if not self.store.save_note(note_id, self._note(text), self._stamp()):
            raise QueryError("note_not_found", "No existe esa nota.", 404)
        return self.detail(idea_id)

    def delete_note(self, idea_id: int, note_id: int) -> dict:
        """Deleting a private note never touches the published events."""
        if not self.store.delete_note(note_id):
            raise QueryError("note_not_found", "No existe esa nota.", 404)
        return self.detail(idea_id)

    @staticmethod
    def _note(text: str) -> str:
        text = (text or "").strip()
        if not text or len(text) > rules.MAX_TEXT:
            raise QueryError("invalid_note", "La nota debe tener entre 1 y 2000 caracteres.", 422)
        return text
