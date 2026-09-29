"""Read-only, outcome-free audit of exact annual capital-allocation facts (#60).

Keep the legacy calculations and all research models frozen. No forward return,
new strategy score, IC or price series is used. A partial cash proxy is not total
shareholder payout; raw comparative shares are not certified split-adjusted.
"""

import argparse
import json
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from . import config
from . import factor_sector_stability as frozen

OUTPUT = config.BASE_DIR / "docs" / "strategy-discovery" / "capital-inputs"
RANKINGS = config.BASE_DIR / "data" / "revalidation_2011_2025" / "acreditado-38"
SIC_SHA256 = "1f48950f7215a23e4d3fe3a05ed051c5d203b480adb6a2857da96c17de69da2d"
TAGS = {
    "buybacks": "PaymentsForRepurchaseOfCommonStock",
    "issuance": "ProceedsFromIssuanceOfCommonStock",
    "options": "ProceedsFromStockOptionsExercised",
    "ocf": "NetCashProvidedByUsedInOperatingActivities",
    "capex": "PaymentsToAcquirePropertyPlantAndEquipment",
    "shares": "CommonStockSharesOutstanding",
}
SPEC: dict = {
    "stage": "INPUT_COVERAGE_ONLY", "version": 1, "tags": TAGS,
    "forms": ["10-K", "10-K/A"], "cutoff": "filing and acceptance dates strictly before signal",
    "anchor": "latest annual filing, no older filing or period fallback; exact SUB.period",
    "maximum_age_days": 550, "annual_duration_days": [330, 400],
    "cash": "same issuer, accession, filing date, form, FP=FY, exact start/end, USD; no absent zeros",
    "duplicates": "exact identical facts deduplicated; contradictory values or dates rejected",
    "proxy": "common repurchases minus disclosed common issuance; not total net payout",
    "options": "separate, no aggregation without non-overlap evidence",
    "fcf": "same period OCF minus nonnegative capex; no substitutes",
    "shares": "positive same-filing common balance instants 330-400 days apart; raw ratio only",
    "split_adjusted_dilution": "not accredited; no entity-attributed split evidence in snapshot",
    "viability": {"minimum_issuers_per_date": 30, "minimum_dates": 30, "minimum_dates_per_window": 8},
    "windows": {name: list(bounds) for name, bounds in frozen.WINDOWS.items()},
    "source_pins": {"rankings": frozen.ORIGINAL_SHA256, "sic": SIC_SHA256},
    "performance_analysis": False, "new_strategy_configurations": 0,
}
ARTIFACTS = {"annual_inputs.csv", "facts_used.csv", "coverage.csv", "filing_periods.csv"}


def save_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def preregister() -> dict:
    record = {"spec": SPEC, "sha256": frozen.fingerprint(SPEC),
              "code_sha256": frozen.file_hash(Path(__file__), text=True),
              "protocol_sha256": frozen.file_hash(OUTPUT / "PROTOCOLO.md", text=True)}
    path = OUTPUT / "preregistro.json"
    if path.exists():
        if json.loads(path.read_text(encoding="utf-8")) != record:
            raise ValueError("El protocolo/motor de inputs de capital ha cambiado.")
    else:
        save_json(path, record)
    return record


def universe() -> tuple[dict[str, pd.DataFrame], dict]:
    """Verify every pinned original file, but read rankings and labels only, no outcomes."""
    original = json.loads((config.BASE_DIR / "docs" / "factor-zoo" / "resultado.json").read_text(encoding="utf-8"))
    if frozen.fingerprint(original) != frozen.ORIGINAL_SHA256:
        raise ValueError("Resultado original modificado.")
    hashes = original["inputs_sha256"]
    ranking_paths = {}
    for name, expected in hashes.items():
        path = config.BASE_DIR.joinpath(*name.replace("\\", "/").split("/"))
        if frozen.file_hash(path) != expected:
            raise ValueError(f"Input original modificado: {name}")
        if path.name.startswith("ranking-"):
            ranking_paths[path.stem.removeprefix("ranking-")] = path
    if len(ranking_paths) != 57 or min(ranking_paths) != "2011-07-02" or max(ranking_paths) != "2025-07-02":
        raise ValueError("Calendario original distinto.")
    frozen.load_saved(SIC_SHA256)
    labels = pd.read_csv(frozen.OUTPUT / "assignments.csv", dtype=str, keep_default_na=False)
    frames = {}
    for day, path in sorted(ranking_paths.items()):
        ranking = pd.read_csv(path, index_col=0, usecols=["symbol", "entity_id", "composite_score", "score_coverage"])
        frame = ranking.loc[ranking.composite_score.notna() & (ranking.score_coverage >= .70), ["entity_id"]].copy()
        assigned = labels.loc[labels.fecha == day].set_index("symbol")
        if (frame.index.has_duplicates or assigned.index.has_duplicates or set(assigned.index) != set(frame.index)
                or not assigned.entity_id.reindex(frame.index).equals(frame.entity_id)):
            raise ValueError(f"Universo/identidad distinto: {day}")
        frame["division"] = assigned.division
        frames[day] = frame
    return frames, hashes


def filing_periods(ciks: set[str]) -> tuple[pd.DataFrame, dict]:
    """Complete primary-registrant SUB metadata with exact fiscal periods, pinned ZIPs."""
    supplement = frozen.load_saved(SIC_SHA256)
    tables, sources = [], {}
    for url, expected in sorted(supplement["sources"].items()):
        name = url.rsplit("/", 1)[-1]
        sub, provenance = frozen._read_archive(config.DATA_DIR / "history_refresh" / "validation_1996_2015" / name, expected)
        sub["cik"] = sub.cik.str.zfill(10)
        selected = sub.loc[sub.cik.isin(ciks) & sub.form.isin(SPEC["forms"])].copy()
        for column in ("filed", "period"):
            selected[column] = selected[column].map(
                lambda value: f"{value[:4]}-{value[4:6]}-{value[6:]}" if re.fullmatch(r"\d{8}", value) else "")
        selected["source_url"] = url
        tables.append(selected.rename(columns={"adsh": "accn", "filed": "filed_date"})[
            ["accn", "cik", "form", "period", "filed_date", "accepted", "fy", "fp", "source_url"]])
        sources[url] = provenance
    if len(sources) != 68:
        raise ValueError("Faltan archivos SEC fijados.")
    combined = pd.concat(tables, ignore_index=True)
    for _, duplicate in combined.loc[combined.accn.duplicated(keep=False)].groupby("accn"):
        if len(duplicate.drop(columns="source_url").drop_duplicates()) != 1:
            raise ValueError("Metadatos contradictorios para un accession.")
    combined = combined.sort_values(["cik", "filed_date", "accepted", "accn", "source_url"]).drop_duplicates("accn")
    return combined.reset_index(drop=True), sources


def read_facts(snapshot: Path, expected: str, entities: set[str]) -> tuple[dict, dict]:
    if frozen.file_hash(snapshot) != expected:
        raise ValueError("Snapshot original modificado.")
    facts: dict = defaultdict(list)
    provenance: dict = {"snapshot_sha256": expected, "fact_rows": 0, "payloads_sha256": ""}
    payloads = []
    tags = list(TAGS.values())
    with sqlite3.connect(snapshot.resolve().as_uri() + "?mode=ro", uri=True) as connection:
        placeholders = ",".join("?" for _ in tags)
        cursor = connection.execute(
            "SELECT entity_id,payload_json,source FROM entity_observations WHERE dataset='edgar_facts' "
            f"AND json_extract(payload_json,'$.tag') IN ({placeholders}) ORDER BY entity_id,record_key,symbol", tags)
        for entity, payload, source in cursor:
            if entity not in entities:
                continue
            fact = json.loads(payload)
            expected_url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{entity[4:]}.json"
            if source != expected_url:
                raise ValueError("Fuente de facts no corresponde al CIK acreditado.")
            digest = frozen.fingerprint(fact)
            record = {**fact, "entity_id": entity, "source_url": source, "payload_sha256": digest}
            facts[(entity, fact["accn"])].append(record)
            payloads.append([entity, digest, source])
    provenance["fact_rows"] = len(payloads)
    provenance["payloads_sha256"] = frozen.fingerprint({"records": sorted(payloads)})
    return dict(facts), provenance


def latest_annual(filings: pd.DataFrame, day: str) -> tuple[dict | None, str]:
    if filings.empty:
        return None, "no_annual_filing"
    group = filings.loc[filings.form.isin(SPEC["forms"])].copy()
    group["_filed"] = pd.to_datetime(group.filed_date, format="%Y-%m-%d", errors="coerce")
    group["_accepted"] = pd.to_datetime(group.accepted, format="mixed", errors="coerce")
    if group._filed.isna().any():
        return None, "unknown_filing_date"
    past = group.loc[group._filed < pd.Timestamp(day)]
    known = past.loc[past._accepted.notna() & (past._accepted.dt.normalize() < pd.Timestamp(day))]
    unknown = past.loc[past._accepted.isna()]
    if not unknown.empty and (known.empty or unknown._filed.max() >= known._filed.max()):
        return None, "unknown_acceptance_date"
    if known.empty:
        return None, "no_prior_annual_filing"
    chosen = known.sort_values(["_filed", "_accepted", "accn"]).iloc[-1]
    period = pd.to_datetime(chosen.period, format="%Y-%m-%d", errors="coerce")
    if pd.isna(period) or period > chosen._filed or period >= pd.Timestamp(day):
        return None, "invalid_fiscal_period"
    if (pd.Timestamp(day) - period).days > SPEC["maximum_age_days"]:
        return chosen.drop(labels=["_filed", "_accepted"]).to_dict(), "stale_annual_filing"
    return chosen.drop(labels=["_filed", "_accepted"]).to_dict(), "current_annual_filing"


def component(facts: list[dict], filing: dict, key: str) -> tuple[dict | None, str]:
    unit = "shares" if key == "shares" else "USD"
    selected = [row for row in facts if row["tag"] == TAGS[key] and row["unit"] == unit
                and row["end_date"] == filing["period"]]
    if not selected:
        return None, "missing"
    valid = []
    for row in selected:
        if (row.get("filed_date") != filing["filed_date"] or row.get("form") != filing["form"]
                or row.get("fp") != "FY" or row.get("accn") != filing["accn"]):
            return None, "metadata_mismatch"
        if key == "shares":
            if row.get("start_date"):
                continue
        else:
            start = pd.to_datetime(row.get("start_date"), format="%Y-%m-%d", errors="coerce")
            if pd.isna(start) or not 330 <= (pd.Timestamp(row["end_date"]) - start).days <= 400:
                continue
        value = row.get("val")
        if value is None or not np.isfinite(value) or (value < 0 and key != "ocf") or (key == "shares" and value == 0):
            return None, "invalid_value"
        valid.append(row)
    if not valid:
        return None, "no_annual_period" if key != "shares" else "no_balance_instant"
    distinct = {(row["start_date"], row["end_date"], row["val"]) for row in valid}
    if len(distinct) > 1:
        return None, "conflicting_fact_or_period"
    return min(valid, key=lambda row: row["payload_sha256"]), "reported"


def pair_value(first: dict | None, second: dict | None) -> tuple[float | None, str]:
    if first is None or second is None:
        return None, "missing_component"
    if (first["start_date"], first["end_date"]) != (second["start_date"], second["end_date"]):
        return None, "period_mismatch"
    return float(first["val"] - second["val"]), "paired"


def annual_row(entity: str, day: str, filings: pd.DataFrame, facts: dict) -> tuple[dict, list[dict]]:
    filing, reason = latest_annual(filings, day)
    result: dict = {"entity_id": entity, "fecha": day, "filing_status": reason, "accn": "", "period": "",
                    "filed_date": "", "accepted": "", "filing_source_url": "",
                    "common_cash_difference_usd": None, "cash_status": "no_current_filing",
                    "fcf_usd": None, "fcf_status": "no_current_filing", "shares_change_raw": None,
                    "shares_status": "no_current_filing", "split_adjusted_dilution": None,
                    "total_net_payout_accredited": False}
    for key in TAGS:
        result.update({key + "_value": None, key + "_start": "", key + "_end": "", key + "_status": "no_current_filing"})
    if filing is None:
        return result, []
    result.update({name: filing[name] for name in ("accn", "period", "filed_date", "accepted")})
    result["filing_source_url"] = filing["source_url"]
    if reason != "current_annual_filing":
        return result, []
    rows = facts.get((entity, filing["accn"]), [])
    used: list[dict] = []
    components = {}
    for key in TAGS:
        row, status = component(rows, filing, key)
        components[key] = row
        result[key + "_status"] = status
        if row is not None:
            result.update({key + "_value": row["val"], key + "_start": row["start_date"], key + "_end": row["end_date"]})
            used.append(row)
    result["common_cash_difference_usd"], result["cash_status"] = pair_value(components["buybacks"], components["issuance"])
    result["fcf_usd"], result["fcf_status"] = pair_value(components["ocf"], components["capex"])
    current = components["shares"]
    if current is None:
        result["shares_status"] = "missing_current_balance"
    else:
        prior = [row for row in rows if row["tag"] == TAGS["shares"] and row["unit"] == "shares"
                 and not row["start_date"] and pd.notna(pd.to_datetime(row["end_date"], errors="coerce"))
                 and 330 <= (pd.Timestamp(filing["period"]) - pd.Timestamp(row["end_date"])).days <= 400]
        previous_values = {(row["end_date"], row["val"]) for row in prior}
        if not prior:
            result["shares_status"] = "missing_prior_balance"
        elif len(previous_values) != 1:
            result["shares_status"] = "conflicting_prior_balance"
        elif any(row.get("filed_date") != filing["filed_date"] or row.get("form") != filing["form"]
                 or row.get("fp") != "FY" or row.get("accn") != filing["accn"] for row in prior):
            result["shares_status"] = "prior_metadata_mismatch"
        elif any(row["val"] is None or not np.isfinite(row["val"]) or row["val"] <= 0 for row in prior):
            result["shares_status"] = "invalid_prior_balance"
        else:
            previous = min(prior, key=lambda row: row["payload_sha256"])
            used.append(previous)
            result.update(shares_change_raw=float(current["val"] / previous["val"] - 1),
                          shares_status="raw_comparative_split_basis_unverified",
                          shares_prior_end=previous["end_date"], shares_prior_value=previous["val"])
    return result, used


def coverage(panel: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for day, quarter in panel.groupby("fecha", sort=True):
        groups = [("all", "all", quarter), *[("division", division, group) for division, group in quarter.groupby("division")]]
        for kind, name, sub in groups:
            issuers = sub.drop_duplicates("entity_id")
            row = {"fecha": day, "stratum": kind, "group": name, "n_universe": len(sub),
                   "n_unique_issuers": len(issuers),
                   "n_cash_pair": int(issuers.common_cash_difference_usd.notna().sum()),
                   "n_fcf_pair": int(issuers.fcf_usd.notna().sum()), "n_joint_cash_fcf": int((issuers.common_cash_difference_usd.notna() & issuers.fcf_usd.notna()).sum()),
                   "n_raw_annual_shares": int(issuers.shares_change_raw.notna().sum()),
                   "n_accredited_dilution": int(issuers.split_adjusted_dilution.notna().sum()),
                   "filing_reasons": json.dumps(dict(Counter(sub.filing_status)), sort_keys=True),
                   "cash_reasons": json.dumps(dict(Counter(sub.cash_status)), sort_keys=True)}
            rows.append(row)
    return pd.DataFrame(rows)


def summary(panel: pd.DataFrame) -> dict:
    all_dates = coverage(panel).query("stratum == 'all'")
    viability = {}
    for key in ("n_cash_pair", "n_fcf_pair", "n_joint_cash_fcf", "n_accredited_dilution"):
        valid = all_dates.loc[all_dates[key] >= 30]
        windows = {name: int(((valid.fecha >= start) & (valid.fecha < end)).sum())
                   for name, (start, end) in frozen.WINDOWS.items()}
        viability[key] = {"minimum_issuers": int(all_dates[key].min()), "maximum_issuers": int(all_dates[key].max()),
                          "n_dates_with_30": len(valid), "windows": windows,
                          "sample_size_gate": len(valid) >= 30 and all(n >= 8 for n in windows.values())}
    return {"n_dates": len(all_dates), "n_security_dates": len(panel),
            "n_issuer_dates": len(panel[["fecha", "entity_id"]].drop_duplicates()), "viability": viability,
            "filing_reasons": dict(Counter(panel.filing_status)), "cash_reasons": dict(Counter(panel.cash_status)),
            "shares_reasons": dict(Counter(panel.shares_status)), "performance_analysis": False,
            "total_net_payout_accredited": False, "split_adjusted_dilution_accredited": False}


def analyze(destination: Path = OUTPUT) -> dict:
    record = preregister()
    if (destination / "resultado.json").exists():
        raise ValueError("La auditoría ya está congelada; no se sobrescribe.")
    frames, original_hashes = universe()
    entities = {entity for frame in frames.values() for entity in frame.entity_id}
    if not all(re.fullmatch(r"cik:\d{10}", entity) for entity in entities):
        raise ValueError("Identidad CIK original incompleta.")
    filings, archives = filing_periods({entity[4:] for entity in entities})
    manifest = json.loads((RANKINGS / "manifest.json").read_text(encoding="utf-8"))
    facts, fact_sources = read_facts(RANKINGS / "snapshot.db", manifest["snapshot_sha256"], entities)
    grouped = {f"cik:{cik}": group for cik, group in filings.groupby("cik", sort=False)}
    annual, used = [], {}
    for day, frame in frames.items():
        cache = {}
        for symbol, source in frame.iterrows():
            entity = source.entity_id
            if entity not in cache:
                cache[entity] = annual_row(entity, day, grouped.get(entity, filings.iloc[:0]), facts)
            row, records = cache[entity]
            annual.append({**row, "symbol": str(symbol), "division": source.division})
            for item in records:
                used[(entity, item["payload_sha256"])] = item
    panel = pd.DataFrame(annual)
    tables = {"annual_inputs.csv": panel, "facts_used.csv": pd.DataFrame(list(used.values())).sort_values(["entity_id", "accn", "tag", "end_date"]),
              "coverage.csv": coverage(panel), "filing_periods.csv": filings}
    destination.mkdir(parents=True, exist_ok=True)
    for name, table in tables.items():
        table.to_csv(destination / name, index=False, lineterminator="\n")
    result = {"spec_sha256": record["sha256"], "code_sha256": record["code_sha256"],
              "protocol_sha256": record["protocol_sha256"], "stage": SPEC["stage"],
              "original_files": original_hashes, "sic_result": SIC_SHA256, "archives": archives,
              "fact_sources": fact_sources, "summary": summary(panel), "new_strategy_configurations": 0,
              "artifacts_sha256": {name: frozen.file_hash(destination / name, text=True) for name in tables},
              "versions": {"pandas": pd.__version__, "numpy": np.__version__},
              "limitations": ["standard Company Facts tags only, no custom disclosures reconstructed",
                              "strict latest filing and period; missing data may be nonrandom",
                              "common cash proxy is not complete net payout; options overlap not established",
                              "raw comparative share ratio has no accredited split basis",
                              "no return, alpha, strategy score or economic performance calculated"]}
    save_json(destination / "resultado.json", result)
    return result


def verify() -> dict:
    if not (OUTPUT / "preregistro.json").exists():
        raise ValueError("Falta el preregistro publicado.")
    record = preregister()
    result = json.loads((OUTPUT / "resultado.json").read_text(encoding="utf-8"))
    for field in ("spec_sha256", "code_sha256", "protocol_sha256"):
        expected = record["sha256"] if field == "spec_sha256" else record[field]
        if result[field] != expected:
            raise ValueError("Sello de auditoría modificado.")
    if set(result["artifacts_sha256"]) != ARTIFACTS:
        raise ValueError("Artefactos incompletos.")
    for name, expected in result["artifacts_sha256"].items():
        if frozen.file_hash(OUTPUT / name, text=True) != expected:
            raise ValueError(f"Artefacto modificado: {name}")
    panel = pd.read_csv(OUTPUT / "annual_inputs.csv", float_precision="round_trip")
    if frozen.fingerprint(summary(panel)) != frozen.fingerprint(result["summary"]):
        raise ValueError("El resumen no reproduce el publicado.")
    if result["summary"]["performance_analysis"] or result["new_strategy_configurations"]:
        raise ValueError("La auditoría no puede simular una estrategia.")
    _, hashes = universe()
    if hashes != result["original_files"]:
        raise ValueError("Fuentes originales distintas.")
    if frozen.file_hash(RANKINGS / "snapshot.db") != result["fact_sources"]["snapshot_sha256"]:
        raise ValueError("Snapshot publicado modificado.")
    for url, expected in result["archives"].items():
        path = config.DATA_DIR / "history_refresh" / "validation_1996_2015" / url.rsplit("/", 1)[-1]
        if frozen.file_hash(path) != expected["sha256"]:
            raise ValueError("Archivo SEC publicado modificado.")
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
        print(json.dumps({"sha256": frozen.fingerprint(result), "summary": result["summary"]}, ensure_ascii=False, indent=2))
