"""Canonical hashing, chain verification and decision replay of the prospective ledger (pure)."""

import hashlib
import json
import math
from datetime import date, datetime

import numpy as np
import pandas as pd

UNREADABLE = object()  # The anchor file exists but cannot be parsed.


def safe(value):
    if isinstance(value, dict):
        return {str(k): safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [safe(v) for v in value]
    if isinstance(value, np.generic):
        return safe(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, (datetime, date, pd.Timestamp)):  # Ranking rows carry next-earnings dates.
        return value.isoformat()
    return value


def canonical(value) -> str:
    return json.dumps(safe(value), sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def fingerprint(value) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def verify_chain(rows, anchor=None, *, require_anchor=True, on_event=None) -> dict:
    """`rows`: (seq, prev_hash, record_hash, payload_json) by seq. `anchor`: the head file
    ({"seq", "hash"}; the empty anchor when absent) or UNREADABLE. `on_event(seq, record_hash,
    payload)` receives each verified row, so a reader parses every payload only once."""
    previous, count = "", 0
    for seq, prev, digest, payload in rows:
        count += 1
        try:
            parsed = json.loads(payload)
            expected = fingerprint({"seq": seq, "prev_hash": prev, "payload": parsed})
        except (TypeError, ValueError):
            return {"ok": False, "reason": "payload ilegible o modificado", "broken_at": seq}
        if seq != count or prev != previous or expected != digest:
            return {"ok": False, "reason": "cadena modificada o con registros eliminados", "broken_at": seq}
        if on_event is not None:
            on_event(seq, digest, parsed)
        previous = digest
    head = {"seq": count, "hash": previous}
    if require_anchor:
        if anchor is UNREADABLE:
            return {"ok": False, "reason": "ancla ilegible", **head}
        if anchor != head:
            return {"ok": False, "reason": "ancla distinta: cola eliminada o commit sin anclar", "anchor": anchor, **head}
    return {"ok": True, **head}


def replay_decision(event: dict | None) -> dict:
    """Replay ranking from frozen blocks, without current source data or scoring code."""
    if event is None or event["payload"].get("kind") != "DECISION" or not event["payload"].get("inputs"):
        raise ValueError("Decisión sin entradas derivadas para reproducir.")
    seq, payload = event["seq"], event["payload"]
    digest = "signal-inputs-v1:" + fingerprint({"inputs": payload["inputs"], "metadata": payload.get("inputs_metadata"),
                                               "sources": payload["sources"], "universe": payload["universe"]})
    table = pd.DataFrame(payload["inputs"]).set_index("symbol")
    weights = payload["configuration"]["weights"]
    values = table.reindex(columns=[b + "_score" for b in weights]).to_numpy(dtype=float)
    w = np.array(list(weights.values()))
    available = np.isfinite(values)
    denominator = available @ w
    scores = np.divide(np.where(available, values, 0) @ w, denominator,
                       out=np.full(len(values), np.nan), where=denominator > 0)
    # Missing Composite can also reflect original eligibility guards.
    saved = table.composite_score.to_numpy(dtype=float)
    scores[~np.isfinite(saved)] = np.nan
    matches = bool(np.allclose(scores, saved, equal_nan=True, atol=1e-8, rtol=0))
    table["replayed"] = scores
    eligible = table.loc[np.isfinite(scores) & (table.score_coverage >= payload["configuration"]["coverage"])]
    ranked = eligible.assign(_symbol=eligible.index).sort_values(["replayed", "_symbol"], ascending=[False, True]).index.tolist()
    return {"seq": seq, "record_hash": event["record_hash"], "fingerprint_matches": digest == payload["data_fingerprint"],
            "scores_match": matches, "ranking_matches": ranked == payload["eligible"],
            "replayed_top_n": ranked[:payload["configuration"]["top_n"]], "actual_top_n": payload["top_n"],
            "status": payload["status"], "model_version": payload["model_version"]}
