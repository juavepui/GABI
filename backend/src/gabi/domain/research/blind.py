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


def disclosure(status: str, unlock_date: str, looks: list[str] | None, today: str) -> dict:
    """What performance a blind validation may show on `today` (ISO dates).

    Without a preregistered plan, as the Streamlit page: everything once the seal is broken or the
    unlock date arrives. With a plan, only at its reviews: performance is computed up to the last
    review reached, never with later quarters, and nothing before the first review. A seal broken
    before this rule existed stays visible, because hiding it would misstate what was already seen.
    """
    if status == "broken_early":
        return {"revealed": True, "through": None, "next_look": None}
    if not looks:
        return {"revealed": today >= unlock_date, "through": None, "next_look": None}
    reached = [look for look in sorted(looks) if today >= look]
    upcoming = [look for look in sorted(looks) if look > today]
    return {"revealed": bool(reached), "through": reached[-1] if reached else None,
            "next_look": upcoming[0] if upcoming else None}
