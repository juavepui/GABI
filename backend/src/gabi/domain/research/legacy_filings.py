"""Conservative, review-assisted extraction from pre-XBRL annual reports.

A pinned review contract supplies table, units and exact reporting periods.
The parser never guesses these from nearby prose or promotes an unreviewed table.
"""
import re
from datetime import date

NUMBER = re.compile(r"\(\s*-?\d[\d,]*(?:\.\d+)?\s*\)|-?\d[\d,]*(?:\.\d+)?|--|[—–\x97]")


def values_after_label(line: str, label: str) -> list[float] | None:
    line = line.replace("\x92", "'").replace("’", "'")
    if not line.lower().startswith(label.lower()):
        return None
    tail = line[len(label):].strip().replace("$", "")
    # No footnotes, ratios, percentages or arbitrary prose in the value columns.
    if NUMBER.sub("", tail).strip():
        return None
    tokens = NUMBER.findall(tail)
    values = []
    for token in tokens:
        if token in {"--", "—", "–", "\x97"}:
            # Dash means no stated number; a reviewed contract may explicitly
            # handle a zero separately. Missing must never silently become zero.
            return None
        clean = token.replace(",", "").replace(" ", "")
        values.append(-float(clean[1:-1]) if clean.startswith("(") else float(clean))
    return values or None


def reviewed_rows(tables: list[list[str]], contract: dict) -> list[dict]:
    """Rows of the reviewed tables (text lines per table) of a filing whose hash was already checked."""
    date.fromisoformat(contract["filed_date"])
    rows: dict = {}
    for spec in contract["tables"]:
        lines = tables[spec["index"]]
        for concept in spec["concepts"]:
            matches = [v for line in lines if (v := values_after_label(line, concept["label"])) is not None]
            if len(matches) != 1 or len(matches[0]) != len(spec["periods"]):
                raise ValueError(f"Ambiguous/missing row or columns: {concept['label']}")
            for period, value in zip(spec["periods"], matches[0], strict=True):
                start, end = period
                date.fromisoformat(end)
                if start:
                    if not 340 <= (date.fromisoformat(end) - date.fromisoformat(start)).days <= 380:
                        raise ValueError("Reviewed annual duration is not annual")
                if end > contract["filed_date"]:
                    raise ValueError("Period ends after publication")
                row = dict(tag=concept["tag"], unit="USD", start_date=start, end_date=end,
                           val=value * spec["scale"], form="10-K", fp="FY", fy=int(contract["fiscal_year"]),
                           filed_date=contract["filed_date"], accn=contract["accn"])
                key = (row["tag"], start, end)
                if key in rows and rows[key]["val"] != row["val"]:
                    raise ValueError("Conflicting reviewed tables")
                rows[key] = row
    for check in contract["checks"]:
        found = [r for r in rows.values() if r["tag"] == check["tag"] and r["end_date"] == check["end_date"]]
        if len(found) != 1 or found[0]["val"] != check["value"]:
            raise ValueError(f"Independent transcription check failed: {check['tag']}")
    for end in {row["end_date"] for row in rows.values()}:
        balance = {row["tag"]: row["val"] for row in rows.values() if row["end_date"] == end and not row["start_date"]}
        if all(tag in balance for tag in ["Assets", "Liabilities", "StockholdersEquity"]):
            if abs(balance["Assets"] - balance["Liabilities"] - balance["StockholdersEquity"]) > 1:
                raise ValueError("Reviewed balance sheet does not reconcile")
    return list(rows.values())
