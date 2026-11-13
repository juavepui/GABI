"""Prospective ledger in Research Lab: verified reads, an explicit report job and append-only evaluations."""

import json
import re
import threading
from collections.abc import Callable, Iterator
from typing import Protocol

from gabi.application.errors import QueryError
from gabi.domain.research.live_ledger import fingerprint, replay_decision, verify_chain

VERSION = re.compile(r"[A-Za-z0-9._:-]{1,128}\Z")
ANCHOR_RACE = "ancla distinta: cola eliminada o commit sin anclar"


class LedgerStore(Protocol):
    def stamp(self) -> tuple: ...
    def scan(self, consume: Callable[[Iterator[tuple], object], dict]) -> dict: ...
    def row(self, seq: int) -> tuple | None: ...


class LedgerWriter(Protocol):
    def save_evaluation(self, report: dict) -> dict: ...


def normalize_live_report(options: dict | None) -> dict:
    version = (options or {}).get("model_version")
    if set(options or {}) != {"model_version"} or not isinstance(version, str) or not VERSION.fullmatch(version):
        raise QueryError("invalid_job", "Indica una versión de modelo válida.", 422)
    return {"model_version": version}


def _summary(seq: int, payload: dict) -> dict:
    return {"seq": seq, "stage": payload.get("stage"), "market_date": payload.get("market_date"),
            "status": payload.get("status"), "candidates": len(payload.get("top_n") or []),
            "git_commit": payload.get("git_commit"), "model_version": payload.get("model_version"),
            "has_inputs": bool(payload.get("inputs"))}


class LiveLedgerQueries:
    def __init__(self, store: LedgerStore, research_mode: Callable[[], bool]):
        self.store, self.research_mode = store, research_mode
        self._lock = threading.Lock()
        self._cache: tuple[tuple, dict] | None = None

    def _require_research(self) -> None:
        if not self.research_mode():
            raise QueryError("research_required", "Research Lab requiere el modo Research local.", 403)

    def _verified(self) -> dict:
        """Full chain verification (as Streamlit did per render), repeated only when the files change."""
        with self._lock:
            stamp = self.store.stamp()
            if self._cache is not None and self._cache[0] == stamp:
                return self._cache[1]
            for _ in range(2):  # A reader can land between the writer's commit and its anchor update.
                state: dict = {"decisions": [], "digests": {}, "evaluations": set(), "kinds": {}}

                def collect(seq: int, digest: str, payload: dict) -> None:
                    state["digests"][seq] = digest
                    kind = payload.get("kind")
                    state["kinds"][kind] = state["kinds"].get(kind, 0) + 1
                    if kind == "DECISION":
                        state["decisions"].append(_summary(seq, payload))
                    elif kind == "EVALUATION":
                        state["evaluations"].add(payload.get("report_sha256"))

                integrity = self.store.scan(lambda rows, anchor: verify_chain(rows, anchor, on_event=collect))
                if integrity["ok"] or integrity["reason"] != ANCHOR_RACE:
                    break
            result = {"integrity": integrity} | state
            self._cache = (stamp, result)  # Pre-scan stamp: a change during the scan forces a rescan.
            return result

    def overview(self) -> dict:
        self._require_research()
        verified = self._verified()
        integrity = verified["integrity"]
        ok = integrity["ok"]
        decisions = verified["decisions"] if ok else []
        return {
            "integrity": {"ok": ok, "reason": integrity.get("reason"), "seq": integrity.get("seq"),
                          "broken_at": integrity.get("broken_at")},
            "n_events": len(verified["digests"]) if ok else 0,
            "events_by_kind": verified["kinds"] if ok else {},
            "decisions": decisions,
            "live_versions": sorted({row["model_version"] for row in decisions if row["stage"] == "LIVE_FORWARD"}),
        }

    def decision(self, seq: int) -> dict:
        event = self.event(seq)
        payload = event["payload"]
        replay, replay_error = None, None
        if payload.get("inputs"):
            try:
                replay = replay_decision(event)
            except (ValueError, KeyError, TypeError) as exc:
                replay_error = str(exc)
        return {"seq": seq, "record_hash": event["record_hash"],
                "summary": _summary(seq, payload) | {"reason": payload.get("reason"),
                                                     "created_at": payload.get("created_at"),
                                                     "top_n": payload.get("top_n") or [],
                                                     "data_fingerprint": payload.get("data_fingerprint"),
                                                     "quality": payload.get("quality")},
                "replay": replay, "replay_error": replay_error}

    def event(self, seq: int) -> dict:
        """One frozen decision, checked against the verified chain before it is shown."""
        self._require_research()
        verified = self._verified()
        if not verified["integrity"]["ok"]:
            raise QueryError("live_ledger_invalid", "El registro prospectivo no está íntegro.", 409)
        if seq not in {row["seq"] for row in verified["decisions"]}:
            raise QueryError("decision_not_found", "La decisión no existe.", 404)
        row = self.store.row(seq)
        if row is None:
            raise QueryError("live_ledger_changed", "El registro prospectivo ha cambiado.", 409)
        _, prev, digest, raw = row
        payload = json.loads(raw)
        if digest != verified["digests"][seq] or fingerprint({"seq": seq, "prev_hash": prev,
                                                               "payload": payload}) != digest:
            raise QueryError("live_ledger_changed", "La decisión no coincide con la cadena verificada.", 409)
        return {"seq": seq, "record_hash": digest, "payload": payload}

    def evaluation_saved(self, report_sha256: str) -> bool:
        return report_sha256 in self._verified()["evaluations"]


class LiveLedgerCommands:
    def __init__(self, queries: LiveLedgerQueries, writer: LedgerWriter, report: Callable[[str], dict]):
        self.queries, self.writer, self.report = queries, writer, report

    def save_evaluation(self, job_id: str) -> dict:
        """Append the verified report of a finished live_forward_report job as a new event."""
        self.queries._require_research()
        report = self.report(job_id)
        if not self.queries.overview()["integrity"]["ok"]:
            raise QueryError("live_ledger_invalid", "El registro prospectivo no está íntegro.", 409)
        if self.queries.evaluation_saved(fingerprint(report)):
            raise QueryError("evaluation_exists", "Esta evaluación ya está guardada en el registro.", 409)
        saved = self.writer.save_evaluation(report)
        return {"seq": saved["seq"], "record_hash": saved["record_hash"], "report_sha256": fingerprint(report)}
