"""Revision 2: quarantine out-of-scope provenance; keep annual audit rules frozen."""

import argparse
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from . import capital_input_audit as base

OUTPUT = base.OUTPUT / "v2"
BASE_SHA256 = "6ee1bd74ab9415f2501137a5e1cc052aaee62b9c74e8f69e4b1e201c3a9dcd6a"
SPEC: dict = {**base.SPEC, "version": 2, "base_code_sha256": BASE_SHA256,
              "source_handling": "exact CIK Company Facts only; quarantine other sources and block their whole accession, no fallback"}
ARTIFACTS = base.ARTIFACTS | {"source_quarantine.csv"}


def preregister() -> dict:
    if base.frozen.file_hash(Path(base.__file__), text=True) != BASE_SHA256:
        raise ValueError("El motor anual original ha cambiado.")
    record = {"spec": SPEC, "sha256": base.frozen.fingerprint(SPEC),
              "code_sha256": base.frozen.file_hash(Path(__file__), text=True),
              "protocol_sha256": base.frozen.file_hash(OUTPUT / "PROTOCOLO.md", text=True),
              "base_protocol_sha256": base.frozen.file_hash(base.OUTPUT / "PROTOCOLO.md", text=True)}
    path = OUTPUT / "preregistro.json"
    if path.exists():
        if json.loads(path.read_text(encoding="utf-8")) != record:
            raise ValueError("Preregistro revisión 2 modificado.")
    else:
        base.save_json(path, record)
    return record


def read_facts(snapshot: Path, expected: str, entities: set[str]) -> tuple[dict, dict, pd.DataFrame, set]:
    if base.frozen.file_hash(snapshot) != expected:
        raise ValueError("Snapshot original modificado.")
    facts: dict = defaultdict(list)
    quarantine, payloads, blocked = [], [], set()
    tags = list(base.TAGS.values())
    with sqlite3.connect(snapshot.resolve().as_uri() + "?mode=ro", uri=True) as connection:
        placeholders = ",".join("?" for _ in tags)
        cursor = connection.execute(
            "SELECT entity_id,payload_json,source FROM entity_observations WHERE dataset='edgar_facts' "
            f"AND json_extract(payload_json,'$.tag') IN ({placeholders}) ORDER BY entity_id,record_key,symbol", tags)
        for entity, payload, source in cursor:
            if entity not in entities:
                continue
            fact = json.loads(payload)
            digest = base.frozen.fingerprint(fact)
            record = {**fact, "entity_id": entity, "source_url": source, "payload_sha256": digest}
            payloads.append([entity, digest, source])
            if source == f"https://data.sec.gov/api/xbrl/companyfacts/CIK{entity[4:]}.json":
                facts[(entity, fact["accn"])].append(record)
            else:
                reason = "unsupported_SEC_instance_source" if str(source).startswith("https://www.sec.gov/Archives/") else "source_not_matching_CIK_CompanyFacts"
                quarantine.append({**record, "source_reason": reason})
                blocked.add((entity, fact["accn"]))
    accepted = sum(len(rows) for rows in facts.values())
    mixed = sum(key in facts for key in blocked)
    for key in blocked:
        facts.pop(key, None)
    provenance = {"snapshot_sha256": expected, "fact_rows": len(payloads), "accepted_source_rows": accepted,
                  "quarantined_source_rows": len(quarantine), "blocked_filing_keys": len(blocked),
                  "mixed_source_filings_blocked": mixed,
                  "usable_source_rows": sum(len(rows) for rows in facts.values()),
                  "payloads_sha256": base.frozen.fingerprint({"records": sorted(payloads)})}
    columns = ["tag", "unit", "start_date", "end_date", "val", "filed_date", "form", "fp", "fy", "accn", "entity_id", "source_url", "payload_sha256", "source_reason"]
    return dict(facts), provenance, pd.DataFrame(quarantine, columns=columns), blocked


def summarize(panel: pd.DataFrame, provenance: dict) -> dict:
    return {**base.summary(panel), "source_provenance": provenance,
            "selected_filing_source_status": dict(Counter(panel.fact_source_status))}


def analyze(destination: Path = OUTPUT) -> dict:
    record = preregister()
    if (destination / "resultado.json").exists():
        raise ValueError("La revisión 2 ya está congelada; no se sobrescribe.")
    frames, hashes = base.universe()
    entities = {entity for frame in frames.values() for entity in frame.entity_id}
    filings, archives = base.filing_periods({entity[4:] for entity in entities})
    manifest = json.loads((base.RANKINGS / "manifest.json").read_text(encoding="utf-8"))
    facts, provenance, quarantine, blocked = read_facts(base.RANKINGS / "snapshot.db", manifest["snapshot_sha256"], entities)
    grouped = {f"cik:{cik}": group for cik, group in filings.groupby("cik", sort=False)}
    annual, used = [], {}
    for day, frame in frames.items():
        cache = {}
        for symbol, source in frame.iterrows():
            entity = source.entity_id
            if entity not in cache:
                row, records = base.annual_row(entity, day, grouped.get(entity, filings.iloc[:0]), facts)
                row["fact_source_status"] = "admitted_source_or_absent"
                if (entity, row["accn"]) in blocked and row["filing_status"] == "current_annual_filing":
                    row["fact_source_status"] = "quarantined_filing"
                    row.update(cash_status="source_quarantined", fcf_status="source_quarantined", shares_status="source_quarantined")
                cache[entity] = row, records
            row, records = cache[entity]
            annual.append({**row, "symbol": str(symbol), "division": source.division})
            for item in records:
                used[(entity, item["payload_sha256"])] = item
    panel = pd.DataFrame(annual)
    used_columns = ["tag", "unit", "start_date", "end_date", "val", "filed_date", "form", "fp", "fy", "accn", "entity_id", "source_url", "payload_sha256"]
    tables = {"annual_inputs.csv": panel, "facts_used.csv": pd.DataFrame(list(used.values()), columns=used_columns).sort_values(["entity_id", "accn", "tag", "end_date"]),
              "coverage.csv": base.coverage(panel), "filing_periods.csv": filings,
              "source_quarantine.csv": quarantine.sort_values(["entity_id", "accn", "tag", "end_date", "payload_sha256"])}
    destination.mkdir(parents=True, exist_ok=True)
    for name, table in tables.items():
        table.to_csv(destination / name, index=False, lineterminator="\n")
    result = {"spec_sha256": record["sha256"], "code_sha256": record["code_sha256"],
              "protocol_sha256": record["protocol_sha256"], "base_protocol_sha256": record["base_protocol_sha256"],
              "base_code_sha256": BASE_SHA256, "stage": SPEC["stage"], "original_files": hashes,
              "sic_result": base.SIC_SHA256, "archives": archives, "fact_sources": provenance,
              "summary": summarize(panel, provenance), "new_strategy_configurations": 0,
              "artifacts_sha256": {name: base.frozen.file_hash(destination / name, text=True) for name in tables},
              "versions": {"pandas": pd.__version__, "numpy": np.__version__},
              "limitations": ["standard Company Facts subset only; historical instance sources quarantined",
                              "nonrandom source/metric missingness, especially disappeared issuers, remains possible",
                              "common cash proxy is not complete net payout; options overlap not established",
                              "raw comparative shares are not accredited split-adjusted dilution",
                              "no performance or new strategy configuration"]}
    base.save_json(destination / "resultado.json", result)
    return result


def verify() -> dict:
    if not (OUTPUT / "preregistro.json").exists():
        raise ValueError("Falta preregistro revisión 2.")
    record = preregister()
    result = json.loads((OUTPUT / "resultado.json").read_text(encoding="utf-8"))
    for field in ("spec_sha256", "code_sha256", "protocol_sha256", "base_protocol_sha256"):
        expected = record["sha256"] if field == "spec_sha256" else record[field]
        if result[field] != expected:
            raise ValueError("Sello revisión 2 modificado.")
    if set(result["artifacts_sha256"]) != ARTIFACTS:
        raise ValueError("Artefactos incompletos.")
    for name, expected in result["artifacts_sha256"].items():
        if base.frozen.file_hash(OUTPUT / name, text=True) != expected:
            raise ValueError(f"Artefacto modificado: {name}")
    panel = pd.read_csv(OUTPUT / "annual_inputs.csv", float_precision="round_trip")
    if base.frozen.fingerprint(summarize(panel, result["fact_sources"])) != base.frozen.fingerprint(result["summary"]):
        raise ValueError("Resumen revisión 2 no reproducido.")
    _, hashes = base.universe()
    if hashes != result["original_files"] or base.frozen.file_hash(base.RANKINGS / "snapshot.db") != result["fact_sources"]["snapshot_sha256"]:
        raise ValueError("Fuentes originales modificadas.")
    for url, expected in result["archives"].items():
        path = base.config.DATA_DIR / "history_refresh" / "validation_1996_2015" / url.rsplit("/", 1)[-1]
        if base.frozen.file_hash(path) != expected["sha256"]:
            raise ValueError("Archivo SEC publicado modificado.")
    if result["summary"]["performance_analysis"] or result["new_strategy_configurations"]:
        raise ValueError("La revisión 2 no puede declarar una estrategia.")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--preregister", action="store_true")
    actions.add_argument("--analyze", action="store_true")
    actions.add_argument("--verify", action="store_true")
    actions.add_argument("--reproduce", type=Path, metavar="DIRECTORY")
    args = parser.parse_args()
    if args.preregister:
        print(json.dumps(preregister(), ensure_ascii=False, indent=2))
    else:
        result = analyze(args.reproduce or OUTPUT) if args.analyze or args.reproduce else verify()
        print(json.dumps({"sha256": base.frozen.fingerprint(result), "summary": result["summary"]}, ensure_ascii=False, indent=2))
