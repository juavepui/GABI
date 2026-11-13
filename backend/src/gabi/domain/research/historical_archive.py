"""Prepare source-attributed archive rows without I/O."""
import json

import pandas as pd

from gabi.domain.market import identity
from gabi.domain.market.sec_identity import ACCREDITED_IDENTITY_TIERS


def prepare_import_membership(source_id: str, frame: pd.DataFrame, start: str, end: str) -> list[tuple]:
    selected = frame[(frame["date"] >= start) & (frame["date"] < end)].copy()
    dates = pd.to_datetime(selected["date"], format="%Y-%m-%d", errors="raise")
    if dates.duplicated().any():
        raise ValueError("Conflicting/duplicate source snapshot dates require review")
    rows = []
    for row in selected.itertuples(index=False):
        members = sorted({s.strip().replace(".", "-") for s in row.tickers.split(",") if s.strip()})
        if not members:
            raise ValueError("Empty source membership")
        rows.append((source_id, row.date, ",".join(members)))
    return rows


def prepare_import_issuer_candidates(source_id: str, frame: pd.DataFrame) -> list[tuple]:
    records = []
    for row in frame.fillna("").itertuples(index=False):
        if row.cik:
            records.append((source_id, row.symbol.replace(".", "-"), row.cik.zfill(10), row.name,
                            row.date_added, row.date_removed, row.created_at))
    return records


def prepare_replace_identity_intervals(source_id: str, rows: list[dict]) -> list[tuple]:
    """Replace one reproducible research tier; never activate operational aliases."""
    allowed = {*ACCREDITED_IDENTITY_TIERS, "ambiguous", "unresolved"}
    records = []
    for row in rows:
        if row["status"] not in allowed:
            raise ValueError("Unknown historical identity tier")
        start, end = row["valid_from"], row["valid_to"]
        if start >= end:
            raise ValueError("Invalid historical identity interval")
        records.append((source_id, identity.normalize_symbol(row["symbol"]),
                        identity.normalize_cik(row["cik"]), start, end, row["status"],
                        row["evidence_count"], row.get("first_filed"), row.get("last_filed"),
                        json.dumps(row.get("source_refs", []), sort_keys=True)))
    return records
