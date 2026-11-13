"""Reviewed aliases, filing-day proof and accredited intervals over supplied rows."""

import json

ACCREDITED_IDENTITY_TIERS = ("confirmed_by_multiple_evidence", "confirmed_historical_ticker",
                             "corroborated_candidate")


def resolve_accredited(symbols: set[str], as_of: str, rows: list[tuple], evidence: list[tuple],
                       intervals: list[tuple]) -> dict[str, dict]:
    candidates: dict[str, dict[str, float]] = {}
    ciks: dict[str, str | None] = {}
    for symbol, entity_id, cik, confidence in rows:
        if symbol in symbols:
            candidates.setdefault(symbol, {})[entity_id] = max(
                confidence, candidates.get(symbol, {}).get(entity_id, 0))
            ciks[entity_id] = cik
    proofs: dict[str, dict[str, tuple[dict, str]]] = {}
    for symbol, entity_id, payload_json, source in evidence:
        payload = json.loads(payload_json)
        if symbol in symbols and payload.get("filed_date") == as_of:
            proofs.setdefault(symbol, {})[entity_id] = (payload, source)
    corroborated: dict[str, dict[str, tuple[str, str]]] = {}
    blocked: set[str] = set()
    for symbol, cik, status, source in intervals:
        if symbol not in symbols:
            continue
        if status == "ambiguous":
            blocked.add(symbol)
        elif status in ACCREDITED_IDENTITY_TIERS:
            corroborated.setdefault(symbol, {})[f"cik:{cik}"] = (status, source)
    result = {}
    for symbol in symbols:
        found = candidates.get(symbol, {})
        status = "ambiguous" if len(found) > 1 else "unresolved"
        entity_id = next(iter(found)) if len(found) == 1 and next(iter(found.values())) >= 0.9 else None
        if entity_id:
            status = "resolved"
        tier = "reviewed_alias" if entity_id else None
        interval = corroborated.get(symbol, {})
        if symbol in blocked or len(interval) > 1 or (interval and found and set(interval) != set(found)):
            entity_id, status, tier = None, "ambiguous", None
        elif len(interval) == 1 and status != "ambiguous":
            entity_id, status = next(iter(interval)), "resolved"
            tier = tier or interval[entity_id][0]
        proof = proofs.get(symbol, {})
        if proof and (len(proof) > 1 or status == "ambiguous" or
                      (found and set(found) != set(proof)) or
                      (interval and set(interval) != set(proof))):
            entity_id, status, tier = None, "ambiguous", None
        elif len(proof) == 1:
            entity_id, status = next(iter(proof)), "resolved"
            tier = "filing_day"
        filing = proof.get(entity_id) if entity_id else None
        result[symbol] = {"entity_id": entity_id,
                          "cik": (ciks.get(entity_id) or entity_id.removeprefix("cik:")) if entity_id else None,
                          "identity_status": status,
                          "identity_tier": tier,
                          "identity_confidence": (1.0 if filing else found.get(entity_id)
                                                  if tier == "reviewed_alias" else None),
                          "identity_source": (filing[1] if filing else interval[entity_id][1]
                                              if tier in ACCREDITED_IDENTITY_TIERS else None),
                          "historical_name": filing[0].get("historical_name") if filing else None}
    return result


def accredited_resolution(row: dict) -> dict:
    resolved = (row["identity_status"] == "resolved" and row["entity_id"] and
                row["identity_tier"] in ACCREDITED_IDENTITY_TIERS)
    return {"entity_id": row["entity_id"] if resolved else None,
            "cik": row["cik"] if resolved else None,
            "status": "resolved" if resolved else
            ("ambiguous" if row["identity_status"] == "ambiguous" else "unresolved"),
            "candidates": [row["entity_id"]] if row["entity_id"] else [],
            "source": row["identity_source"] or "historical_identity_interval",
            "confidence": 1.0 if resolved else None,
            "identity_tier": row["identity_tier"]}
