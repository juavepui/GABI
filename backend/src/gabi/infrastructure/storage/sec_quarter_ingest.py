"""Local adapters for SEC quarter/instance ingestion: read-only selection, XML decoding, reports and backup."""

import json
import os
import tempfile
from pathlib import Path

import pandas as pd
from lxml import etree

from gabi.infrastructure.storage.bounded_reads import bounded_rows, read_only

XBRL = {"x": "http://www.xbrl.org/2003/instance"}


def decode_instance(content: bytes) -> tuple[list[tuple], list[tuple], list[tuple]]:
    """Plain contexts, units and top-level fact nodes of an XBRL instance; no interpretation."""
    parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False)
    root = etree.fromstring(content, parser)
    contexts = []
    for context in root.findall("x:context", XBRL):
        identifier = context.find("x:entity/x:identifier", XBRL)
        dimensional = context.find("x:entity/x:segment", XBRL) is not None or context.find("x:scenario", XBRL) is not None
        period = context.find("x:period", XBRL)
        dates = (None, None, None) if period is None else tuple(
            period.findtext(f"x:{tag}", namespaces=XBRL) for tag in ["instant", "startDate", "endDate"])
        contexts.append((context.get("id"), None if identifier is None else identifier.text or "",
                         dimensional, period is not None, *dates))
    units = [(unit.get("id"), [measure.text for measure in unit.findall("x:measure", XBRL)],
              unit.find("x:divide", XBRL) is not None) for unit in root.findall("x:unit", XBRL)]
    nodes = []
    for node in root:
        if isinstance(node.tag, str):
            qname = etree.QName(node)
            nodes.append((qname.localname, qname.namespace, node.get("contextRef"), node.get("unitRef"), node.text))
    return contexts, units, nodes


class SqliteSecIngestSelection:
    """Read-only selection inputs; absent tables mean absent evidence, never schema creation."""

    def __init__(self, path: Path, *, max_rows: int = 2_000_000, max_bytes: int = 512 * 1024 * 1024,
                 max_field_bytes: int = 64 * 1024):
        if min(max_rows, max_bytes, max_field_bytes) < 1:
            raise ValueError("Invalid SEC ingest selection limits")
        self.path, self.max_rows, self.max_bytes, self.max_field_bytes = path, max_rows, max_bytes, max_field_bytes

    def _rows(self, db, query, params=()):
        return bounded_rows(db, query, params, max_rows=self.max_rows, max_bytes=self.max_bytes,
                            max_field_bytes=self.max_field_bytes)

    def _column(self, table: str, query: str, params=()) -> set:
        with read_only(self.path, self.max_field_bytes) as (db, tables):
            if db is None or table not in tables:
                return set()
            return {row[0] for row in self._rows(db, query, params)}

    def candidate_ciks_before(self, day: str) -> set[str]:
        return self._column("historical_issuer_candidates", "SELECT DISTINCT cik FROM historical_issuer_candidates "
                            "WHERE observed_from<?", (day,))

    def period_candidate_ciks(self, source_id: str, start: str, end_exclusive: str) -> set[str]:
        return self._column("historical_issuer_candidates", "SELECT DISTINCT cik FROM historical_issuer_candidates "
                            "WHERE source_id=? AND cik<>'' AND replace(date_added,'*','')<? AND (date_removed IS NULL "
                            "OR date_removed='' OR replace(date_removed,'*','')>=?)", (source_id, end_exclusive, start))

    def bulk_ciks_filed(self, start: str, end_exclusive: str) -> set[str]:
        return self._column("sec_bulk_submissions", "SELECT DISTINCT cik FROM sec_bulk_submissions "
                            "WHERE filed_date>=? AND filed_date<?", (start, end_exclusive))

    def _table_rows(self, required: set[str], query: str, params=()) -> list[tuple]:
        with read_only(self.path, self.max_field_bytes) as (db, tables):
            return self._rows(db, query, params) if db is not None and required <= tables else []

    def period_candidates(self, source_id: str, start: str, end_exclusive: str) -> list[tuple]:
        return self._table_rows({"historical_issuer_candidates"}, "SELECT DISTINCT symbol,cik,date_added,date_removed "
                                "FROM historical_issuer_candidates WHERE source_id=? AND date_added<? AND "
                                "(date_removed IS NULL OR date_removed='' OR date_removed>=?)",
                                (source_id, end_exclusive, start))

    def period_filings(self, start: str, end_exclusive: str) -> list[tuple]:
        return self._table_rows({"sec_bulk_submissions"}, "SELECT accn,cik,filed_date,instance FROM sec_bulk_submissions "
                                "WHERE filed_date>=? AND filed_date<? AND form IN ('10-K','10-Q') "
                                "AND instance IS NOT NULL ORDER BY filed_date,accn", (start, end_exclusive))

    def intervals(self, source_id: str, statuses: tuple[str, ...]) -> list[tuple]:
        marks = ",".join("?" for _ in statuses)
        return self._table_rows({"historical_identity_intervals"}, "SELECT symbol,cik,valid_from,valid_to,status "
                                f"FROM historical_identity_intervals WHERE source_id=? AND status IN ({marks})",
                                (source_id, *statuses))

    def unresolved_ciks_with_filings(self, source_id: str, minimum: int = 2) -> list[str]:
        rows = self._table_rows({"historical_identity_intervals", "sec_bulk_submissions"},
                                "SELECT DISTINCT cik FROM historical_identity_intervals WHERE source_id=? "
                                "AND status='unresolved' AND cik IN (SELECT cik FROM sec_bulk_submissions "
                                "GROUP BY cik HAVING COUNT(*)>=?) ORDER BY cik", (source_id, minimum))
        return [row[0] for row in rows]

    def submissions(self, forms: list[str]) -> pd.DataFrame:
        with read_only(self.path, self.max_field_bytes) as (db, tables):
            if db is None or "sec_bulk_submissions" not in tables:
                raise ValueError("No hay presentaciones SEC indexadas.")
            columns = [row[1] for row in db.execute("PRAGMA table_info(sec_bulk_submissions)")]
            marks = ",".join("?" for _ in forms)
            rows = self._rows(db, f"SELECT * FROM sec_bulk_submissions WHERE form IN ({marks}) ORDER BY filed_date,accn",
                              tuple(forms))
        return pd.DataFrame.from_records(rows, columns=columns, coerce_float=True)

    def accessions_with_facts(self) -> set:
        with read_only(self.path, self.max_field_bytes) as (db, tables):
            if db is None:
                return set()
            parts = [query for table, query in (
                ("edgar_facts", "SELECT DISTINCT accn FROM edgar_facts"),
                ("historical_facts", "SELECT DISTINCT json_extract(payload_json,'$.accn') FROM historical_facts"),
            ) if table in tables]
            return {row[0] for row in self._rows(db, " UNION ".join(parts))} if parts else set()


class JsonQuarterReport:
    """Per-key checkpoint report; each save replaces the file atomically."""

    def __init__(self, path: Path):
        self.path = path

    def load(self) -> dict:
        return json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}

    def save(self, report: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(dir=self.path.parent, prefix=f".{self.path.name}.", suffix=".tmp")
        try:
            # Text mode keeps the platform newlines these reports were always written with.
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                stream.write(json.dumps(report, indent=2) + "\n")
            os.replace(temporary, self.path)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise
