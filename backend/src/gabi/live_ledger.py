"""Frozen prospective decisions, chained SQLite events and an external head anchor."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from contextlib import contextmanager
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from gabi.domain.research.live_ledger import UNREADABLE, canonical, fingerprint, replay_decision, safe, verify_chain

from . import app_mode, config, edgar, identity, research_lab, storage
from .history_refresh import last_completed_session

STAGES = ("RETROSPECTIVE", "OOS", "LIVE_FORWARD")
SCHEMA = """
CREATE TABLE IF NOT EXISTS live_ledger (
    seq INTEGER PRIMARY KEY, prev_hash TEXT NOT NULL, record_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS live_ledger_no_update BEFORE UPDATE ON live_ledger
BEGIN SELECT RAISE(ABORT, 'live ledger is append-only'); END;
CREATE TRIGGER IF NOT EXISTS live_ledger_no_delete BEFORE DELETE ON live_ledger
BEGIN SELECT RAISE(ABORT, 'live ledger is append-only'); END;
"""


def _now() -> datetime:
    return datetime.now(UTC)


_safe = safe  # Public names kept for existing callers.


def anchor_path():
    return config.DATA_DIR / "live_ledger" / "head.json"


@contextmanager
def _locked():
    directory = anchor_path().parent
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "writer.lock").open("a+b") as lock:
        lock.seek(0, os.SEEK_END)
        if lock.tell() == 0:
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        if sys.platform == "win32":
            import msvcrt
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            getattr(fcntl, "flock")(lock.fileno(), getattr(fcntl, "LOCK_EX") | getattr(fcntl, "LOCK_NB"))
        try:
            yield
        finally:
            lock.seek(0)
            if sys.platform == "win32":
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                getattr(fcntl, "flock")(lock.fileno(), getattr(fcntl, "LOCK_UN"))


def _write_anchor(seq: int, digest: str) -> None:
    path = anchor_path()
    pending = path.with_suffix(".json.tmp")
    with pending.open("w", encoding="utf-8") as stream:
        stream.write(canonical({"seq": seq, "hash": digest}) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    pending.replace(path)


def _verify(conn, *, require_anchor=True) -> dict:
    rows = conn.execute("SELECT seq,prev_hash,record_hash,payload_json FROM live_ledger ORDER BY seq")
    anchor = None
    if require_anchor:
        try:
            anchor = json.loads(anchor_path().read_text(encoding="utf-8")) if anchor_path().exists() else {"seq": 0, "hash": ""}
        except (OSError, ValueError):
            anchor = UNREADABLE
    return verify_chain(rows, anchor, require_anchor=require_anchor)


def verify_integrity() -> dict:
    with _locked(), storage.get_connection() as conn:
        conn.executescript(SCHEMA)
        return _verify(conn)


def _append(payload: dict, *, recover=False) -> dict:
    with _locked(), storage.get_connection() as conn:
        conn.executescript(SCHEMA)
        conn.execute("BEGIN IMMEDIATE")
        integrity = _verify(conn, require_anchor=not recover)
        if not integrity["ok"]:
            raise ValueError(f"Ledger no íntegro: {integrity['reason']}")
        if recover:
            old = payload["previous_anchor"]
            current = json.loads(anchor_path().read_text(encoding="utf-8")) if anchor_path().exists() else {"seq": 0, "hash": ""}
            row = conn.execute("SELECT record_hash FROM live_ledger WHERE seq=?", (old["seq"],)).fetchone()
            if current != old or old["seq"] > integrity["seq"] or (old["seq"] and (not row or row[0] != old["hash"])):
                raise ValueError("El prefijo del ancla cambió durante la recuperación.")
        seq, previous = integrity["seq"] + 1, integrity["hash"]
        payload = _safe(payload)
        digest = fingerprint({"seq": seq, "prev_hash": previous, "payload": payload})
        conn.execute("INSERT INTO live_ledger VALUES (?,?,?,?)", (seq, previous, digest, canonical(payload)))
        conn.commit()
        _write_anchor(seq, digest)
    return {"seq": seq, "record_hash": digest, "payload": payload}


def events() -> list[dict]:
    with _locked(), storage.get_connection() as conn:
        conn.executescript(SCHEMA)
        check = _verify(conn)
        if not check["ok"]:
            raise ValueError(f"Ledger no íntegro: {check['reason']}")
        return [{"seq": r[0], "record_hash": r[1], "payload": json.loads(r[2])}
                for r in conn.execute("SELECT seq,record_hash,payload_json FROM live_ledger ORDER BY seq")]


def append_decision(payload: dict, *, stage="LIVE_FORWARD", created_at: str | None = None) -> dict:
    if stage not in STAGES:
        raise ValueError("Fase inválida.")
    now = _now()
    timestamp = datetime.fromisoformat(created_at) if created_at else now
    if timestamp.tzinfo is None:
        raise ValueError("Timestamp con zona horaria requerido.")
    if stage == "LIVE_FORWARD" and abs((timestamp - now).total_seconds()) > 5:
        raise ValueError("LIVE_FORWARD debe capturarse ahora; no admite fechas históricas.")
    if stage == "LIVE_FORWARD" and payload["market_date"] != last_completed_session(timestamp):
        raise ValueError("La fecha de mercado no coincide con la última sesión cerrada.")
    return _append({**payload, "kind": "DECISION", "stage": stage, "created_at": timestamp.isoformat()})


def append_correction(seq: int, reason: str, changes: dict) -> dict:
    if not reason.strip():
        raise ValueError("La corrección requiere un motivo.")
    original = next((e for e in events() if e["seq"] == seq), None)
    if original is None:
        raise ValueError("No existe el evento original.")
    return _append({"kind": "CORRECTION", "created_at": _now().isoformat(), "original_seq": seq,
                    "original_hash": original["record_hash"], "reason": reason, "changes": changes})


def recover_anchor(reason: str) -> dict:
    """Explicit recovery only if the old anchor is a valid prefix, never for deletion."""
    if not reason.strip():
        raise ValueError("La recuperación requiere un motivo.")
    with _locked(), storage.get_connection() as conn:
        conn.executescript(SCHEMA)
        check = _verify(conn, require_anchor=False)
        if not check["ok"]:
            raise ValueError("Cadena rota; no se puede recuperar el ancla.")
        old = json.loads(anchor_path().read_text(encoding="utf-8")) if anchor_path().exists() else {"seq": 0, "hash": ""}
        row = conn.execute("SELECT record_hash FROM live_ledger WHERE seq=?", (old["seq"],)).fetchone()
        if old["seq"] > check["seq"] or (old["seq"] and (not row or row[0] != old["hash"])):
            raise ValueError("Ancla no es prefijo de la cadena; no se puede ocultar una eliminación.")
    return _append({"kind": "ANCHOR_RECOVERY", "created_at": _now().isoformat(), "previous_anchor": old,
                    "reason": reason}, recover=True)


def provenance(symbols: list[str]) -> dict:
    """Dates actually used in the current derived screener, without hashing 83 GiB."""
    fundamentals = storage.get_fundamentals_fetched_at(symbols)
    sec = edgar.get_edgar_fetched_at(symbols)
    with storage.get_connection() as conn:
        conn.executescript(storage.SCHEMA)
        result = {}
        for symbol in symbols:
            price = conn.execute("SELECT date,close,adj_close FROM prices WHERE symbol=? "
                                 "AND adj_close>0 ORDER BY date DESC LIMIT 1", (symbol,)).fetchone()
            result[symbol] = {"price_date": price[0] if price else None, "close": price[1] if price else None,
                              "adj_close": price[2] if price else None,
                              "fundamentals_fetched_at": fundamentals.get(symbol), "sec_fetched_at": sec.get(symbol)}
    return _safe(result)


def model_metadata(*, weights: dict | None = None, universe_id="SP500_CURRENT") -> dict:
    names = ("scoring.py", "domain/market/scoring.py", "metrics.py", "domain/market/fundamentals.py", "technicals.py", "domain/market/technicals.py",
             "risk.py", "domain/market/risk.py", "screener.py", "edgar.py", "domain/market/sec_facts.py",
             "live_ledger.py", "domain/research/live_performance.py", "evidence_confidence.py", "domain/market/evidence.py",
             "application/market/evidence_assessment.py", "evidence_catalog.py",
             "workspace.py", "__init__.py")
    hashes = {n: hashlib.sha256((config.BASE_DIR / "src" / "gabi" / n).read_text(encoding="utf-8").encode()).hexdigest() for n in names}
    specification = {"weights": weights if weights is not None else app_mode.FROZEN_WEIGHTS,
                     "universe_id": universe_id, "top_n": 20, "coverage": .70,
                     "ranking": "descending composite, ascending ticker", "report_cost_per_side": .001}
    try:
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "backend/src/gabi"], cwd=config.BASE_DIR,
                                    capture_output=True, text=True, timeout=5).stdout)
    except OSError:
        dirty = None
    return {"model_id": app_mode.FROZEN_MODEL_ID, "configuration": specification,
            "config_version": fingerprint(specification), "model_version": fingerprint({"spec": specification, "code": hashes}),
            "git_commit": research_lab._current_git_commit(), "working_tree_modified": dirty,
            "code_sha256": hashes, "dependencies": research_lab._dependency_versions(),
            "environment_fingerprint": research_lab._env_fingerprint()}


def capture_current(*, run_error: str | None = None, maintenance: dict | None = None) -> dict:
    """Read cached inputs and append the actual current decision, including failures."""
    from . import evidence_confidence, screener

    now = _now()
    market = last_completed_session(now)
    payload = {"market_date": market, **model_metadata(), "status": "ERROR", "reason": run_error,
               "universe": [], "eligible": [], "ranking": [], "top_n": [], "excluded": {}, "sources": {},
               "inputs": [], "maintenance": maintenance or {}, "quality": {"fresh": False}}
    try:
        universe = screener.get_universe()
        symbols = universe.symbol.tolist()
        table = screener.build_screener_table(universe, weights=app_mode.FROZEN_WEIGHTS)
        if table.empty:
            table = table.reindex(columns=["composite_score", "score_coverage"])
        if table.index.has_duplicates:
            raise ValueError("Universo con tickers duplicados.")
        sources = _safe(table.attrs.get("sources") or provenance([*symbols, config.BENCHMARK_SYMBOL]))
        for symbol in symbols:
            sources.setdefault(symbol, {})["entity_id"] = identity.resolve(symbol, market)["entity_id"]
        excluded = {}
        for symbol, row in table.iterrows():
            reasons = []
            if not pd.notna(row.get("composite_score")) or not np.isfinite(row.get("composite_score", np.nan)):
                reasons.append("score no disponible")
            if not pd.notna(row.get("score_coverage")) or row.get("score_coverage", 0) < .70:
                reasons.append("cobertura inferior al 70 %")
            if reasons:
                excluded[symbol] = reasons
        eligible = table.drop(index=list(excluded))
        eligible = eligible.assign(_symbol=eligible.index).sort_values(["composite_score", "_symbol"], ascending=[False, True]).drop(columns="_symbol")
        picks = eligible.head(20).index.tolist()
        stale = [s for s in [*picks, config.BENCHMARK_SYMBOL]
                 if sources.get(s, {}).get("price_date") != market
                 or any(not isinstance(sources.get(s, {}).get(k), (int, float)) or sources[s][k] <= 0
                        for k in ("close", "adj_close"))]
        future = [s for s, source in sources.items() if source.get("price_date") and source["price_date"] > market]
        stale_inputs = []
        for symbol in picks:
            for field, hours in (("fundamentals_fetched_at", config.CACHE_MAX_AGE_HOURS),
                                 ("sec_fetched_at", config.EDGAR_CACHE_MAX_AGE_HOURS)):
                value = sources.get(symbol, {}).get(field)
                try:
                    age = (now - datetime.fromisoformat(value)).total_seconds() / 3600 if value else None
                except (TypeError, ValueError):
                    age = None
                if age is None or age < 0 or age > hours:
                    stale_inputs.append(f"{symbol}:{field}")
        maintenance = maintenance or {}
        source_failures = maintenance.get("failed", {})
        failed_events = maintenance.get("failed_events", [])
        failed_inputs = [f"{s}:{field}" for s, failures in source_failures.items() for field in failures
                         if s in picks or (s == config.BENCHMARK_SYMBOL and field == "precio")]
        failed_inputs.extend("universo" for e in failed_events if e.get("source") == "universe")
        failed_count = max(maintenance.get("fallos", 0), maintenance.get("sync", {}).get("statuses", {}).get("failed", 0))
        if failed_count and not source_failures and not failed_events:
            failed_inputs.append("fallos sin atribución de fuente")
        maintenance_failures = len(failed_inputs)
        status = "ERROR" if run_error else "NO_SIGNAL" if not picks else "DEGRADED" if stale or future or stale_inputs or maintenance_failures else "SIGNAL"
        inputs = table.rename_axis("symbol").reset_index().to_dict("records")
        payload.update({"status": status, "reason": run_error or ("fallos parciales del mantenimiento" if maintenance_failures else "datos caducados/futuros/desconocidos" if stale or future or stale_inputs else None),
                        "universe": universe.to_dict("records"), "eligible": eligible.index.tolist(),
                        "ranking": eligible.rename_axis("symbol").reset_index().to_dict("records"),
                        "proposed_top_n": picks, "top_n": picks if status == "SIGNAL" else [], "excluded": excluded,
                        "sources": sources, "inputs": inputs,
                        "inputs_metadata": {"risk_free_rate": table.attrs.get("risk_free_rate")},
                        "quality": {"fresh": not stale and not future and not stale_inputs and not maintenance_failures,
                                    "maintenance_failures": maintenance_failures, "stale_symbols": stale,
                                    "failed_inputs": failed_inputs,
                                    "future_symbols": future, "stale_inputs": stale_inputs}})
    except Exception as exc:
        payload["reason"] = f"{run_error or ''} {type(exc).__name__}: {exc}".strip()
    timestamp = _now()
    actual_market = last_completed_session(timestamp)
    if actual_market != payload["market_date"]:
        payload.update(status="DEGRADED", reason="cambió la sesión cerrada durante el cálculo", top_n=[], market_date=actual_market)
        payload["quality"]["fresh"] = False
    payload["data_fingerprint"] = "signal-inputs-v1:" + fingerprint({"inputs": payload["inputs"], "metadata": payload.get("inputs_metadata"), "sources": payload["sources"],
                                                                 "universe": payload["universe"]})
    payload["evidence"] = {}
    if payload["inputs"]:
        try:
            context = {k: payload[k] for k in ("model_id", "model_version", "config_version", "git_commit", "data_fingerprint")}
            table.attrs["sources"] = payload["sources"]
            evidence = evidence_confidence.build(table, app_mode.FROZEN_WEIGHTS, now=timestamp, market_date=actual_market, context=context)
            payload["evidence"] = {s: evidence[s] for s in payload.get("proposed_top_n", [])}
        except Exception as exc:
            payload["evidence_error"] = f"{type(exc).__name__}: {exc}"
    timestamp = _now()
    if last_completed_session(timestamp) != actual_market:
        payload.update(status="DEGRADED", reason="cambió la sesión durante el diagnóstico de evidencia", top_n=[],
                       market_date=last_completed_session(timestamp))
        payload["quality"]["fresh"] = False
    return append_decision(payload, created_at=timestamp.isoformat())


def save_evaluation(report: dict) -> dict:
    return _append({"kind": "EVALUATION", "created_at": _now().isoformat(), "report": report,
                    "report_sha256": fingerprint(report)})


def reproduce_decision(seq: int) -> dict:
    """Replay ranking from frozen blocks, without current source data or scoring code."""
    event = next((e for e in events() if e["seq"] == seq and e["payload"]["kind"] == "DECISION"), None)
    return replay_decision(event)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--recover-anchor", metavar="REASON")
    args = parser.parse_args()
    print(canonical(recover_anchor(args.recover_anchor) if args.recover_anchor else verify_integrity()))
