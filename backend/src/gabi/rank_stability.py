"""Fixed, outcome-free local weight sensitivity (STAT-8 / issue 51)."""

import argparse
import hashlib
import json

import numpy as np
import pandas as pd
from scipy.stats import kendalltau, spearmanr

from . import config, research_lab, scoring

OUTPUT = config.BASE_DIR / "docs" / "rank-stability"
SPEC_SHA256 = "cd1b011f049cb1913bc3c99d02820cccd55e6ee7760b463e5e4da84932766a9b"
BLOCKS = tuple(scoring.DEFAULT_WEIGHTS)
TOPS = (10, 20, 30)


def perturbations(weights: dict | None = None) -> pd.DataFrame:
    """All feasible directed transfers; the finite family is never optimized."""
    weights = scoring.DEFAULT_WEIGHTS if weights is None else weights
    if set(weights) != set(BLOCKS):
        raise ValueError("Se requieren exactamente los cuatro pesos del modelo.")
    base = np.array([weights.get(b, 0) for b in BLOCKS], dtype=float)
    if not np.isfinite(base).all() or (base < 0).any() or not np.isclose(base.sum(), 1, atol=1e-10, rtol=0):
        raise ValueError("Los cuatro pesos deben ser finitos, no negativos y sumar uno.")
    rows = []
    for donor in range(4):
        for receiver in range(4):
            if donor == receiver:
                continue
            for delta in (.01, .02):
                if base[donor] + 1e-12 < delta:
                    continue
                w = base.copy()
                w[donor] = max(0, w[donor] - delta)
                w[receiver] += delta
                rows.append({"perturbation": f"{BLOCKS[donor]}->{BLOCKS[receiver]}:{delta:.2f}",
                             **dict(zip(BLOCKS, w, strict=True))})
    return pd.DataFrame(rows).set_index("perturbation")


def _ranks(values: np.ndarray, weights: np.ndarray, symbols: np.ndarray) -> np.ndarray:
    valid = np.isfinite(values)
    den = valid @ weights
    scores = np.divide(np.where(valid, values, 0) @ weights, den,
                       out=np.full(len(values), np.nan), where=den > 0)
    if not np.isfinite(scores).all():
        raise ValueError("Hay empresas sin bloques disponibles con peso positivo.")
    order = np.lexsort((symbols, -np.round(scores, 12)))
    ranks = np.empty(len(order), dtype=int)
    ranks[order] = np.arange(1, len(order) + 1)
    return ranks


def analyze(frame: pd.DataFrame, weights: dict | None = None) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    """Return summary, every perturbation's metrics, and every firm's dispersion.

    Coverage eligibility is independent of subsequent returns and UI filters.
    Percentiles and the eligible universe stay fixed across perturbations.
    """
    neighborhood = perturbations(weights)
    weights = scoring.DEFAULT_WEIGHTS if weights is None else weights
    required = [*(f"{b}_score" for b in BLOCKS), "composite_score", "score_coverage"]
    if any(c not in frame for c in required):
        raise ValueError("Faltan bloques, composite_score o score_coverage.")
    if frame.index.has_duplicates or frame.index.isna().any():
        raise ValueError("Los identificadores de empresa deben ser únicos y no vacíos.")
    symbols_all = frame.index.astype(str)
    if symbols_all.has_duplicates or any(not s.strip() for s in symbols_all):
        raise ValueError("Los identificadores de empresa deben ser únicos y no vacíos.")
    data = frame.copy()
    data.index = symbols_all
    numeric = data[required].astype(float)
    eligible = np.isfinite(numeric.composite_score) & (numeric.score_coverage >= .70)
    eligible &= np.isfinite(numeric[[f"{b}_score" for b in BLOCKS[:3]]]).all(axis=1)
    data = data.loc[eligible].sort_index()
    if len(data) < 2:
        raise ValueError("Se necesitan al menos dos empresas elegibles con cobertura del 70 %.")
    values = data[[f"{b}_score" for b in BLOCKS]].to_numpy(dtype=float)
    symbols = data.index.to_numpy()
    base = _ranks(values, np.array([weights[b] for b in BLOCKS]), symbols)
    ranks = np.stack([_ranks(values, w, symbols) for w in neighborhood.to_numpy()])
    sectors = data.get("sector", pd.Series(index=data.index, dtype=object)).replace("", np.nan)
    rows = []
    for name, candidate in zip(neighborhood.index, ranks, strict=True):
        row = {"perturbation": name, "spearman": float(spearmanr(base, candidate).statistic),
               "kendall": float(kendalltau(base, candidate).statistic)}
        for top in TOPS:
            if len(data) <= top:
                continue
            original, changed = base <= top, candidate <= top
            kept = int((original & changed).sum())
            row.update({f"top{top}_overlap": kept / top, f"top{top}_jaccard": kept / (2 * top - kept),
                        f"top{top}_entries": top - kept, f"top{top}_exits": top - kept,
                        f"top{top}_turnover": (top - kept) / top, f"top{top}_company_hhi": 1 / top})
            if sectors.loc[original | changed].notna().all():
                a = sectors.loc[original].value_counts() / top
                b = sectors.loc[changed].value_counts() / top
                sector_mix = pd.concat([a, b], axis=1).fillna(0)
                row.update({f"top{top}_sector_hhi_base": float((a * a).sum()),
                            f"top{top}_sector_hhi": float((b * b).sum()),
                            f"top{top}_sector_max_change": float((sector_mix.iloc[:, 0] - sector_mix.iloc[:, 1]).abs().max())})
        rows.append(row)
    metrics = pd.DataFrame(rows).set_index("perturbation")
    companies = pd.DataFrame({"base_rank": base, "rank_min": ranks.min(axis=0), "rank_max": ranks.max(axis=0),
                              "rank_std": ranks.std(axis=0)}, index=data.index)
    for top in TOPS:
        if len(data) > top:
            companies[f"top{top}_inclusion"] = (ranks <= top).mean(axis=0)
    if "top20_inclusion" in companies:
        inclusion = companies.top20_inclusion
        companies["diagnosis"] = np.select(
            [(base <= 20) & (inclusion == 1), base <= 20, inclusion > 0],
            ["Persistente (Top-20)", "Frágil (Top-20)", "Cerca del Top-20"], default="Fuera del Top-20")
    else:
        companies["diagnosis"] = "Top-20 no estimable"
    companies = companies.sort_values("base_rank")
    summary = {"eligible": len(data), "excluded": len(frame) - len(data), "weights": weights,
               "perturbations": len(neighborhood), "omitted_infeasible": 24 - len(neighborhood),
               "stability_score": float(100 * metrics.top20_overlap.mean()) if "top20_overlap" in metrics else None,
               "metrics": {c: {"mean": float(metrics[c].mean()), "min": float(metrics[c].min()),
                               "max": float(metrics[c].max()), "available": int(metrics[c].count())} for c in metrics},
               "unavailable_tops": [top for top in TOPS if len(data) <= top],
               "sectors_complete": bool(sectors.notna().all()),
               "interpretation": "Fragilidad estructural; no evidencia predictiva ni probabilidad futura."}
    return summary, metrics, companies


def analyze_saved() -> dict:
    """The preregistered 57 rankings, without reading any forward-return file."""
    spec = json.loads((OUTPUT / "preregistro.json").read_text(encoding="utf-8"))
    digest = hashlib.sha256(json.dumps(spec, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    if digest != SPEC_SHA256:
        raise ValueError("La especificación cambió tras el preregistro.")
    root = config.DATA_DIR / "revalidation_2011_2025" / "acreditado-38"
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    dates = [d for d in manifest["dates"] if "2011-07-02" <= d <= "2025-07-02"]
    if len(dates) != 57 or len(set(dates)) != 57:
        raise ValueError("Se esperaban las 57 fechas preregistradas, sin duplicados.")
    inputs = {str(manifest_path.relative_to(config.BASE_DIR)): hashlib.sha256(manifest_path.read_bytes()).hexdigest()}
    all_metrics, all_companies, summaries = [], [], []
    for date in dates:
        path = root / f"ranking-{date}.csv"
        inputs[str(path.relative_to(config.BASE_DIR))] = hashlib.sha256(path.read_bytes()).hexdigest()
        summary, metrics, companies = analyze(pd.read_csv(path, index_col=0), spec["weights"])
        summaries.append({"date": date, **summary})
        all_metrics.append(metrics.reset_index().assign(date=date))
        all_companies.append(companies.rename_axis("symbol").reset_index().assign(date=date))
    metrics = pd.concat(all_metrics, ignore_index=True)
    companies = pd.concat(all_companies, ignore_index=True)
    # Aggregate dates equally (not firms or perturbations from differently sized universes).
    by_date = metrics.drop(columns="perturbation").groupby("date").mean()
    aggregate = {c: {"mean": float(by_date[c].mean()), "min": float(by_date[c].min()),
                     "max": float(by_date[c].max())} for c in by_date}
    files = {"perturbations.csv": perturbations(spec["weights"]).reset_index(),
             "metrics.csv": metrics, "companies.csv": companies,
             "by-date.csv": by_date.reset_index()}
    artifacts = {}
    for name, df in files.items():
        path = OUTPUT / name
        df.to_csv(path, index=False, lineterminator="\n")
        artifacts[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    result = {"issue": 51, "stage": spec["stage"], "spec_sha256": digest,
              "git_commit": research_lab._current_git_commit(), "input_sha256": inputs,
              "artifact_sha256": artifacts, "dates": summaries, "aggregate": aggregate,
              "stability_score": 100 * aggregate["top20_overlap"]["mean"],
              "limitations": [spec["interpretation"], spec["sectors"],
                              "Historical ranks were already inspected in earlier research; this is descriptive, not new OOS."]}
    (OUTPUT / "resultado.json").write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                                          encoding="utf-8")
    return result


def load_saved() -> dict:
    result = json.loads((OUTPUT / "resultado.json").read_text(encoding="utf-8"))
    if result["spec_sha256"] != SPEC_SHA256:
        raise ValueError("Huella de especificación incorrecta.")
    for name, expected in result["artifact_sha256"].items():
        if hashlib.sha256((OUTPUT / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Artefacto alterado: {name}")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analyze", action="store_true", required=True)
    parser.parse_args()
    result = analyze_saved()
    print(json.dumps({"dates": len(result["dates"]), "stability_score": result["stability_score"],
                      "aggregate": result["aggregate"]}, indent=2))
