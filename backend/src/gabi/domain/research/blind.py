"""Canonical blind-validation seals shared by legacy and new readers."""

import hashlib
import json


def canonical_payload(rebalance_date: str, symbols: list, entry_prices: dict) -> str:
    return json.dumps({
        "rebalance_date": rebalance_date,
        "symbols": sorted(symbols),
        "entry_prices": {s: entry_prices[s] for s in sorted(entry_prices)},
    }, sort_keys=True)


def verify_chain(periods: list[dict]) -> dict:
    prev_hash = None
    for period in periods:
        payload = canonical_payload(period["rebalance_date"], json.loads(period["symbols_json"]),
                                    json.loads(period["entry_prices_json"]))
        expected = hashlib.sha256(f"{prev_hash or ''}{payload}".encode()).hexdigest()
        if expected != period["record_hash"] or period["prev_hash"] != prev_hash:
            return {"ok": False, "broken_at": period["rebalance_date"], "n_periods": len(periods)}
        prev_hash = period["record_hash"]
    return {"ok": True, "broken_at": None, "n_periods": len(periods)}
