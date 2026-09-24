"""Conservative, review-assisted extraction from pre-XBRL annual reports.

A pinned review contract supplies table, units and exact reporting periods.
The parser never guesses these from nearby prose or promotes an unreviewed table.
"""
import hashlib
import html as html_std
import json
import re
from datetime import date
from pathlib import Path

from lxml import html

from . import historical_archive
from .sec_history import DIRECTORY, download

TABLES = re.compile(r"<table\b[^>]*>.*?</table\s*>", re.I | re.S)
NUMBER = re.compile(r"\(\s*-?\d[\d,]*(?:\.\d+)?\s*\)|-?\d[\d,]*(?:\.\d+)?|--|[—–\x97]")


def table_lines(source: str) -> list[list[str]]:
    tables = []
    for match in TABLES.finditer(source):
        markup = match.group()
        if re.search(r"<tr\b", markup, re.I):
            node = html.fromstring(markup)
            lines = [" ".join(row.text_content().split()) for row in node.xpath(".//tr")]
        else:
            text = html_std.unescape(re.sub(r"<[^>]+>", " ", markup))
            lines = [" ".join(line.split()) for line in text.splitlines() if line.strip()]
        tables.append(lines)
    return tables


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


def extract_reviewed(content: bytes, contract: dict) -> list[dict]:
    if hashlib.sha256(content).hexdigest() != contract["sha256"]:
        raise ValueError("Filing differs from the reviewed document")
    date.fromisoformat(contract["filed_date"])
    tables = table_lines(content.decode(contract.get("encoding", "cp1252"), errors="replace"))
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


def run_pilot() -> dict:
    manifest = Path(__file__).with_name("resources") / "legacy_filings_pilot.json"
    report = {}
    for contract in json.loads(manifest.read_text(encoding="utf-8")):
        path = download(contract["url"], DIRECTORY / "legacy" / contract["filename"])
        rows = extract_reviewed(path.read_bytes(), contract)
        source = "legacy-reviewed:" + contract["accn"]
        historical_archive.register_source(source, {"url": contract["url"], "sha256": contract["sha256"],
                                                    "review": "table/units/periods and transcription checks",
                                                    "start": "1996-01-01", "end_exclusive": "2009-01-01"})
        historical_archive.import_sec_facts(source, contract["symbol"], contract["cik"], rows, source_url=contract["url"])
        report[contract["symbol"]] = {"rows": len(rows), "checks": len(contract["checks"]),
                                      "filed_date": contract["filed_date"], "url": contract["url"], "status": "passed"}
    (DIRECTORY / "legacy_pilot_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    run_pilot()
