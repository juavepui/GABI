"""Frozen #48 supplement: descriptive IC within dated SEC SIC divisions.

Only local archived filings and the already published Factor Zoo inputs are read.
No operational database writes, downloads, ranking changes or new significance tests.
"""

import argparse
import hashlib
import io
import json
import re
import sqlite3
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import scipy
from scipy import stats

from . import config

OUTPUT = config.BASE_DIR / "docs" / "factor-zoo-sector"
SPEC_SHA256 = "6a417e8f9f31b69a7a8c201a7afe7700227a0898d5df0d29abeab9dc8b9d8097"
ORIGINAL_SHA256 = "84f76e03bbe676d80ae5b0c4ae3af031b6a50fd23f7536b842e1f03df409bee0"
SPEC_COMMIT = "0b88752"
DIVISION_NAMES = {
    "A": "Agricultura, silvicultura y pesca", "B": "Minería", "C": "Construcción",
    "D": "Manufactura", "E": "Transporte, comunicaciones y servicios públicos",
    "F": "Comercio mayorista", "G": "Comercio minorista",
    "H": "Finanzas, seguros e inmobiliario", "I": "Servicios", "J": "Administración pública",
}
WINDOWS = {"2011-15": ("2011-01-01", "2016-01-01"),
           "2016-20": ("2016-01-01", "2021-01-01"), "2021-25": ("2021-01-01", "2026-01-01")}
FILING_COLUMNS = ["accn", "cik", "sic", "form", "filed_date", "accepted", "source_url"]


def fingerprint(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def file_hash(path: Path, *, text: bool = False) -> str:
    """Raw archive/input bytes; normalized newlines for Git-managed text outputs."""
    if text:
        return hashlib.sha256(path.read_text(encoding="utf-8").encode()).hexdigest()
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def specification() -> dict:
    spec = json.loads((OUTPUT / "preregistro.json").read_text(encoding="utf-8"))
    if fingerprint(spec) != SPEC_SHA256:
        raise ValueError("El preregistro SIC difiere del publicado.")
    return spec


def sic_division(value, divisions: dict) -> str | None:
    raw = str(value).strip()
    if not re.fullmatch(r"\d{3,4}", raw):
        return None
    code = int(raw)
    return next((name for name, (low, high) in divisions.items() if low <= code <= high), None)


def _filing_dates(filings: pd.DataFrame) -> pd.DataFrame:
    result = filings.copy()
    # SUB accepted may include fractional seconds. Compare calendar dates conservatively.
    result["_filed"] = pd.to_datetime(result.filed_date, format="%Y-%m-%d", errors="coerce")
    result["_accepted"] = pd.to_datetime(result.accepted, format="mixed", errors="coerce")
    return result


def assign(frame: pd.DataFrame, date: str, filings: pd.DataFrame, spec: dict) -> pd.DataFrame:
    """No ticker lookup, future labels, co-registrants, or older-valid-label fallback."""
    if frame.index.has_duplicates:
        raise ValueError("Ranking con símbolos duplicados.")
    filings = _filing_dates(filings)
    grouped = {str(cik): group for cik, group in filings.groupby("cik", sort=False)}
    signal = pd.Timestamp(date)
    rows = []
    for symbol, entity in frame.entity_id.items():
        row = {"fecha": date, "symbol": str(symbol), "entity_id": str(entity), "cik": "",
               "accn": "", "filed_date": "", "accepted": "", "sic": "", "division": "",
               "source_url": "", "reason": "missing_identity"}
        if not re.fullmatch(r"cik:\d{10}", str(entity)):
            rows.append(row)
            continue
        row["cik"] = str(entity)[4:]
        group = grouped.get(row["cik"])
        row["reason"] = "no_prior_filing"
        if group is None:
            rows.append(row)
            continue
        if group._filed.isna().any():
            row["reason"] = "unknown_filing_date"
            rows.append(row)
            continue
        past = group.loc[(group._filed < signal) & group.form.isin(spec["forms"])]
        # A missing acceptance date might conceal a newer label: do not silently fall back.
        if not past.empty and past._accepted.isna().any():
            missing = past.loc[past._accepted.isna()]
            known = past.loc[past._accepted.notna() & (past._accepted.dt.normalize() < signal)]
            if known.empty or missing._filed.max() >= known._filed.max():
                row["reason"] = "unknown_acceptance_date"
                rows.append(row)
                continue
        past = past.loc[past._accepted.notna() & (past._accepted.dt.normalize() < signal)]
        if past.empty:
            rows.append(row)
            continue
        latest = past.loc[past._filed == past._filed.max()]
        latest = latest.loc[latest._accepted == latest._accepted.max()]
        chosen = latest.sort_values("accn").iloc[0]
        row.update({key: str(chosen[key]) for key in FILING_COLUMNS})
        if (latest.sic.nunique(dropna=False) > 1):
            row["reason"] = "ambiguous_latest_sic"
        elif (signal - chosen._filed).days > spec["max_age_days"]:
            row["reason"] = "stale_filing"
        elif chosen._accepted.normalize() < chosen._filed:
            row["reason"] = "inconsistent_dates"
        else:
            division = sic_division(chosen.sic, spec["divisions"])
            row["reason"] = "classified" if division else "invalid_or_unclassified_sic"
            row["division"] = division or ""
        rows.append(row)
    return pd.DataFrame(rows).set_index("symbol")


def verify_archive(path: Path, expected: dict, indexed: pd.DataFrame) -> dict:
    """Validate primary registrant metadata against original SUB and the full ZIP hash."""
    if path.stat().st_size != expected["bytes"] or file_hash(path) != expected["sha256"]:
        raise ValueError(f"Archivo SEC modificado: {path.name}")
    with zipfile.ZipFile(path) as archive:
        raw = archive.read("sub.txt")
    sub = pd.read_csv(io.BytesIO(raw), sep="\t", dtype=str, keep_default_na=False)
    if sub.adsh.duplicated().any() or indexed.accn.duplicated().any():
        raise ValueError(f"Accession duplicado: {path.name}")
    sub = sub.set_index("adsh")
    for filing in indexed.to_dict("records"):
        if filing["accn"] not in sub.index:
            raise ValueError(f"Filing no encontrado en SUB: {filing['accn']}")
        original = sub.loc[filing["accn"]]
        filed = str(original["filed"])
        filed = f"{filed[:4]}-{filed[4:6]}-{filed[6:]}" if re.fullmatch(r"\d{8}", filed) else ""
        values = {"cik": str(original["cik"]).zfill(10), "sic": str(original["sic"]),
                  "form": str(original["form"]), "filed_date": filed, "accepted": str(original["accepted"])}
        if any(str(filing[key]) != value for key, value in values.items()):
            raise ValueError(f"Metadatos SEC distintos de SUB: {filing['accn']}")
    return {"sha256": expected["sha256"], "bytes": expected["bytes"],
            "sub_sha256": hashlib.sha256(raw).hexdigest(), "verified_filings": len(indexed),
            "fetched_at": expected["fetched_at"]}


def archived_filings(ciks: set[str], snapshot: dict | None = None) -> tuple[pd.DataFrame, dict]:
    if snapshot is None:
        uri = config.DB_PATH.resolve().as_uri() + "?mode=ro"
        with sqlite3.connect(uri, uri=True) as connection:
            connection.execute("BEGIN")
            filings = pd.read_sql_query("SELECT " + ",".join(FILING_COLUMNS) + " FROM sec_bulk_submissions", connection)
            archive_rows = pd.read_sql_query("SELECT * FROM sec_archive_files", connection).to_dict("records")
        archives = {r["url"]: r for r in archive_rows}
    else:
        filings = pd.read_csv(OUTPUT / "filings.csv", dtype=str, keep_default_na=False)
        archives = snapshot["sources"]
    filings = filings.loc[filings.cik.isin(ciks)].fillna("").sort_values(["cik", "filed_date", "accepted", "accn"])
    hashes = {}
    for url, group in filings.groupby("source_url", sort=True):
        name = str(url).rsplit("/", 1)[-1]
        if not re.fullmatch(r"20\d{2}q[1-4]\.zip", name) or url not in archives:
            raise ValueError(f"Fuente SEC sin archivo registrado: {url}")
        path = config.DATA_DIR / "history_refresh" / "validation_1996_2015" / name
        hashes[str(url)] = verify_archive(path, archives[url], group)
    return filings.reset_index(drop=True), hashes


def frozen_frames() -> tuple[dict[str, pd.DataFrame], dict]:
    path = config.BASE_DIR / "docs" / "factor-zoo" / "resultado.json"
    original = json.loads(path.read_text(encoding="utf-8"))
    if fingerprint(original) != ORIGINAL_SHA256:
        raise ValueError("El resultado original de #48 ha cambiado.")
    inputs = original["inputs_sha256"]
    # Verify the complete set BEFORE reading outcomes or doing any statistics.
    paths = {name: config.BASE_DIR.joinpath(*name.replace("\\", "/").split("/")) for name in inputs}
    for name, source in paths.items():
        if file_hash(source) != inputs[name]:
            raise ValueError(f"Input congelado modificado: {name}")
    ranking_paths = {p.stem.removeprefix("ranking-"): p for p in paths.values() if p.name.startswith("ranking-")}
    return_paths = {p.stem.removeprefix("forward-"): p for p in paths.values() if p.name.startswith("forward-")}
    if (len(ranking_paths) != 57 or set(ranking_paths) != set(return_paths)
            or min(ranking_paths) != "2011-07-02" or max(ranking_paths) != "2025-07-02"):
        raise ValueError("Calendario congelado de #48 distinto.")
    frames = {}
    spec = specification()
    for date, ranking_path in sorted(ranking_paths.items()):
        ranking = pd.read_csv(ranking_path, index_col=0)
        eligible = ranking.loc[ranking.composite_score.notna() & (ranking.score_coverage >= .70)]
        forward = pd.read_csv(return_paths[date], index_col=0)
        if eligible.index.has_duplicates or forward.index.has_duplicates or set(eligible.index) != set(forward.index):
            raise ValueError(f"Universo congelado distinto: {date}")
        columns = ["entity_id", *[metric + "_pct" for metric in spec["signals"]]]
        frames[date] = eligible[columns].join(forward[["retorno"]], validate="one_to_one")
    return frames, inputs


def quarter_rows(frame: pd.DataFrame, date: str, metric: str, spec: dict) -> list[dict]:
    column = metric + "_pct"
    rows = []
    for division in spec["divisions"]:
        group = frame.loc[frame.division == division]
        numeric = group[[column, "retorno"]].replace([np.inf, -np.inf], np.nan)
        pairs = numeric.dropna()
        status = "estimable"
        ic = None
        if len(pairs) < spec["minimum_pairs"]:
            status = "insufficient_pairs"
        elif pairs[column].nunique() < 2 or pairs.retorno.nunique() < 2:
            status = "constant_series"
        else:
            ic = float(stats.spearmanr(pairs[column], pairs.retorno).statistic)
        rows.append({"fecha": date, "metric": metric, "division": division,
                     "n_eligible": len(group), "n_signal": int(numeric[column].notna().sum()),
                     "n_return": int(numeric.retorno.notna().sum()), "n_pairs": len(pairs), "ic": ic, "status": status})
    return rows


def summary(panel: pd.DataFrame, spec: dict) -> dict:
    def describe(part: pd.DataFrame) -> dict:
        valid = part.loc[part.ic.notna()]
        n = len(valid)
        deviation = float(valid.ic.std(ddof=1)) if n > 1 else 0
        return {"n_periods": n, "n_calendar_periods": len(part), "n_pairs": int(valid.n_pairs.sum()),
                "ic_mean": float(valid.ic.mean()) if n else None,
                "icir": float(valid.ic.mean() / deviation) if deviation > 0 else None,
                "positive_fraction": float((valid.ic > 0).mean()) if n else None,
                "status": "sufficient_periods" if n >= spec["minimum_summary_periods"] else "insufficient_periods"}

    result: dict = {}
    for metric in spec["signals"]:
        result[metric] = {}
        for division in spec["divisions"]:
            part = panel.loc[(panel.metric == metric) & (panel.division == division)]
            result[metric][division] = {**describe(part), "name": DIVISION_NAMES[division],
                                        "windows": {name: describe(part.loc[(part.fecha >= start) & (part.fecha < end)])
                                                    for name, (start, end) in WINDOWS.items()}}
    return result


def coverage_rows(frame: pd.DataFrame, date: str) -> list[dict]:
    """Retain missing outcomes in the coverage denominator and publish both strata."""
    finite_return = pd.Series(np.isfinite(pd.to_numeric(frame.retorno, errors="coerce")), index=frame.index)
    rows = []
    for label, selected in (("all", frame), ("return_available", frame.loc[finite_return]),
                            ("return_missing", frame.loc[~finite_return])):
        rows.append({"fecha": date, "stratum": label, "n_eligible": len(selected),
                     "n_identity": int(selected.cik.ne("").sum()), "n_selected_filing": int(selected.accn.ne("").sum()),
                     "n_classified": int(selected.division.ne("").sum()),
                     "classified_fraction": float(selected.division.ne("").mean()) if len(selected) else None,
                     "reasons": selected.reason.value_counts().sort_index().to_dict()})
    return rows


def factor_coverage_rows(frame: pd.DataFrame, date: str, spec: dict) -> list[dict]:
    rows = []
    for metric in spec["signals"]:
        numeric = frame[[metric + "_pct", "retorno"]].replace([np.inf, -np.inf], np.nan)
        paired = numeric.notna().all(axis=1)
        classified = frame.division.ne("")
        rows.append({"fecha": date, "metric": metric, "n_eligible": len(frame),
                     "n_signal": int(numeric.iloc[:, 0].notna().sum()), "n_return": int(numeric.retorno.notna().sum()),
                     "n_pairs": int(paired.sum()), "n_classified_pairs": int((paired & classified).sum()),
                     "n_unknown_division_pairs": int((paired & ~classified).sum())})
    return rows


def analyze(destination: Path | None = None, snapshot: dict | None = None) -> dict:
    destination = destination or OUTPUT
    if (destination / "resultado.json").exists():
        raise ValueError("El suplemento ya está congelado; se consulta sin sobrescribirlo.")
    spec = specification()
    frames, inputs = frozen_frames()
    ciks = {str(entity)[4:] for frame in frames.values() for entity in frame.entity_id
            if re.fullmatch(r"cik:\d{10}", str(entity))}
    filings, sources = archived_filings(ciks, snapshot)
    assignments, rows, coverage, factor_coverage = [], [], [], []
    for date, frame in frames.items():
        assigned = assign(frame, date, filings, spec)
        joined = frame.join(assigned.drop(columns="entity_id"), validate="one_to_one")
        saved = assigned.copy()
        saved["return_available"] = np.isfinite(pd.to_numeric(frame.retorno, errors="coerce"))
        assignments.append(saved.reset_index())
        coverage.extend(coverage_rows(joined, date))
        factor_coverage.extend(factor_coverage_rows(joined, date, spec))
        for metric in spec["signals"]:
            rows.extend(quarter_rows(joined, date, metric, spec))
    panel = pd.DataFrame(rows)
    tables = {"filings.csv": filings, "assignments.csv": pd.concat(assignments, ignore_index=True),
              "sector_ic.csv": panel, "factor_coverage.csv": pd.DataFrame(factor_coverage),
              "coverage.csv": pd.DataFrame([{**r, "reasons": json.dumps(r["reasons"], sort_keys=True)} for r in coverage])}
    destination.mkdir(parents=True, exist_ok=True)
    for name, table in tables.items():
        table.to_csv(destination / name, index=False, lineterminator="\n")
    result = {"spec_sha256": SPEC_SHA256, "spec_commit": SPEC_COMMIT,
              "code_sha256": file_hash(Path(__file__), text=True), "original_result_sha256": ORIGINAL_SHA256,
              "inputs_sha256": inputs, "sources": sources, "n_dates": len(frames),
              "versions": {"pandas": pd.__version__, "numpy": np.__version__, "scipy": scipy.__version__},
              "taxonomy": "SEC dated SIC divisions A–J; not GICS", "stage": spec["stage"],
              "minimum_pairs": spec["minimum_pairs"], "minimum_summary_periods": spec["minimum_summary_periods"],
              "factors": summary(panel, spec), "coverage": coverage,
              "artifacts_sha256": {name: file_hash(destination / name, text=True) for name in tables},
              "interpretation": spec["evidence"], "preservation": spec["preservation"]}
    (destination / "resultado.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return result


def load_saved(expected_sha256: str) -> dict:
    """UI reads only the pinned supplement and its text artifacts; never reanalyzes."""
    result = json.loads((OUTPUT / "resultado.json").read_text(encoding="utf-8"))
    if fingerprint(result) != expected_sha256 or result["spec_sha256"] != SPEC_SHA256:
        raise ValueError("Suplemento SIC modificado.")
    specification()
    if result["code_sha256"] != file_hash(Path(__file__), text=True):
        raise ValueError("Código del suplemento SIC modificado.")
    for name, expected in result["artifacts_sha256"].items():
        if name not in {"filings.csv", "assignments.csv", "sector_ic.csv", "coverage.csv", "factor_coverage.csv"} or file_hash(OUTPUT / name, text=True) != expected:
            raise ValueError(f"Artefacto SIC modificado: {name}")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--analyze", action="store_true")
    actions.add_argument("--verify", action="store_true")
    actions.add_argument("--reproduce", type=Path, metavar="DIRECTORY")
    args = parser.parse_args()
    if args.analyze:
        result = analyze()
    else:
        from . import evidence_catalog

        catalogue = evidence_catalog.load()
        if not catalogue.get("sources", {}).get("factor-zoo-sector"):
            raise ValueError("Suplemento ausente del catálogo publicado.")
        result = load_saved(catalogue["sources"]["factor-zoo-sector"]["sha256"])
        if args.reproduce:
            reproduced = analyze(args.reproduce, snapshot=result)
            if fingerprint(reproduced) != fingerprint(result):
                raise ValueError("La reproducción difiere; consultar artefactos sin alterar el resultado publicado.")
    all_coverage = [r for r in result["coverage"] if r["stratum"] == "all"]
    print(json.dumps({"sha256": fingerprint(result), "n_dates": result["n_dates"],
                      "n_eligible": sum(r["n_eligible"] for r in all_coverage),
                      "n_classified": sum(r["n_classified"] for r in all_coverage)}, indent=2))
