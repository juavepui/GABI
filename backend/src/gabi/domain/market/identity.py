"""Resolve current dated alias claims, preserving the legacy conservative rule."""

import re
from datetime import date

import pandas as pd

MIN_CONFIDENCE = 0.9


def normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper().replace(".", "-")


def normalize_cik(cik) -> str:
    value = str(cik).strip()
    if not value.isdigit() or len(value) > 10 or int(value) == 0:
        raise ValueError("CIK must contain 1-10 digits and be nonzero")
    return value.zfill(10)


def entity_definition(cik, name: str | None, entity_id: str | None, local_id: str) -> tuple[str, str | None, str | None]:
    cik = normalize_cik(cik) if cik is not None else None
    name = None if pd.isna(name) else name
    derived = f"cik:{cik}" if cik else entity_id or f"local:{local_id}"
    if cik and entity_id and entity_id != derived:
        raise ValueError("entity_id conflicts with CIK")
    return derived, cik, name


def require_same_cik(existing: tuple | None, cik: str | None) -> None:
    if existing and existing[0] != cik:
        raise ValueError("An entity's CIK cannot be reassigned")


def alias_evidence(symbol: str, valid_from: str, valid_to: str | None, source: str, confidence: float) -> tuple:
    start = date.fromisoformat(valid_from).isoformat()
    end = date.fromisoformat(valid_to).isoformat() if valid_to else None
    if not source.strip() or not 0 <= confidence <= 1 or (end and end <= start):
        raise ValueError("Invalid alias evidence, confidence or validity interval")
    symbol = normalize_symbol(symbol)
    if not symbol:
        raise ValueError("Empty symbol")
    return symbol, start, end, source, confidence


def name_matches(historical_name: str, submissions: dict) -> bool:
    def key(name):
        return re.sub(r"[^a-z0-9]", "", name.casefold())
    names = [submissions.get("name", ""), *[row.get("name", "") for row in submissions.get("formerNames", [])]]
    return bool(historical_name and key(historical_name) in {key(name) for name in names if name})


def aliases_overlap(aliases: list[tuple], first: str, second: str) -> bool:
    return any(a_start < (b_end or "9999-12-31") and b_start < (a_end or "9999-12-31")
               for a_symbol, a_start, a_end, _ in aliases if a_symbol == first
               for b_symbol, b_start, b_end, _ in aliases if b_symbol == second)


def attributed_prices(frame: pd.DataFrame, requested: str, aliases: list[tuple], conflicts: list[tuple]) -> pd.DataFrame:
    """Keep one attributed security series, within the issuer's verified life."""
    if frame.empty:
        return frame
    sources = set(frame["source_symbol"])
    if requested in sources:
        frame = frame[frame["source_symbol"] == requested]
    elif len(sources) == 1:
        if aliases_overlap(aliases, requested, next(iter(sources))):
            return pd.DataFrame()
    else:
        return pd.DataFrame()
    mask = pd.Series(False, index=frame.index)
    for _, start, end, confidence in aliases:
        if confidence >= MIN_CONFIDENCE:
            mask |= (frame["date"] >= start) & (frame["date"] < (end or "9999-12-31"))
    for start, end in conflicts:
        mask &= ~((frame["date"] >= start) & (frame["date"] < (end or "9999-12-31")))
    frame = frame[mask].copy()
    source_symbol = str(frame["source_symbol"].iloc[0]) if not frame.empty else requested
    frame["date"] = pd.to_datetime(frame["date"])
    result = frame.drop(columns=["source_symbol"]).set_index("date").sort_index()
    result.attrs["source_symbol"] = source_symbol
    return result


def resolve_claims(claims: list[tuple], as_of) -> dict:
    candidates = sorted({claim[0] for claim in claims})
    chosen = max(claims, key=lambda claim: claim[3]) if claims else None
    status = "ambiguous" if len(candidates) > 1 else "unresolved"
    if len(candidates) == 1 and chosen and chosen[3] >= MIN_CONFIDENCE:
        status = "resolved"
    return {"entity_id": chosen[0] if chosen and status == "resolved" else None,
            "cik": chosen[1] if chosen and status == "resolved" else None,
            "status": status, "candidates": candidates, "source": chosen[2] if chosen else None,
            "confidence": chosen[3] if chosen else None, "as_of": as_of}


DATA_KEYS = {
    "prices": ("date",), "splits": ("date",), "fundamentals": ("fetched_at",),
    "edgar_facts": ("tag", "unit", "start_date", "end_date", "accn"),
    "sector": ("effective_date",), "filing_identity": ("accession",),
}


def _json_value(value):
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if pd.isna(value):
        return None
    return value.item() if hasattr(value, "item") else value
