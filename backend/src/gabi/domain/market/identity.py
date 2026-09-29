"""Resolve current dated alias claims, preserving the legacy conservative rule."""


def resolve_claims(claims: list[tuple], as_of) -> dict:
    candidates = sorted({claim[0] for claim in claims})
    chosen = max(claims, key=lambda claim: claim[3]) if claims else None
    status = "ambiguous" if len(candidates) > 1 else "unresolved"
    if len(candidates) == 1 and chosen and chosen[3] >= 0.9:
        status = "resolved"
    return {"entity_id": chosen[0] if chosen and status == "resolved" else None,
            "cik": chosen[1] if chosen and status == "resolved" else None,
            "status": status, "candidates": candidates, "source": chosen[2] if chosen else None,
            "confidence": chosen[3] if chosen else None, "as_of": as_of}
