"""STAT-6 (#49): controles nulos y perturbaciones reproducibles de estrategias Top-N."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from . import config, cross_section_test as cs, historical_revalidation as hr, scoring, stats_rigor


OUTPUT = config.BASE_DIR / "docs" / "placebo-engine"
BLOCKS = ("value_score", "quality_score", "momentum_score", "risk_score")
BASE_WEIGHTS = tuple(scoring.DEFAULT_WEIGHTS[x] for x in ("value", "quality", "momentum", "risk"))
STABILITY_WINDOWS = (("2011-07-02", "2016-01-02"), ("2016-01-02", "2021-01-02"),
                     ("2021-01-02", "2025-10-02"))
SPEC = {
    "issue": 49, "stage": "RESEARCH_RETROSPECTIVE",
    "target": "Composite vigente Top-20 equiponderado trimestral, 57 periodos de #40, retornos brutos",
    "inputs": "rankings acreditado-38 y forward returns de #40; solo elegibles con retorno observado; sectores faltantes en categoría unknown",
    "seed": 490047, "n_simulations": 2048, "top_n": 20,
    "inferential_nulls": {
        "random_ranking": "permutar orden de todas las elegibles dentro de cada trimestre y elegir Top-N; preserva retornos y shocks de cada trimestre",
        "random_top_n": "muestra uniforme Top-N sin reemplazo en cada trimestre; equivalente en distribución a ranking aleatorio, seed independiente",
        "sector_neutral_top_n": "muestra uniforme por sector dentro de cada trimestre conservando los conteos sectoriales del Top-N observado",
    },
    "diagnostic_null": "permutar retornos entre empresas del mismo sector y trimestre, manteniendo fija la selección; no preserva autocorrelación idiosincrática",
    "perturbations": {
        "date_lag": "usar el ranking del rebalanceo anterior para el trimestre actual; se comparan 56 periodos, sin lookahead",
        "weights": "256 vectores generados antes de ver retornos; delta uniforme +/-0,025 por bloque, centrado a suma cero y reescalado a máximo absoluto 0,025; no se optimizan",
        "inverse_sign": "últimas N empresas del Composite; sanity check único",
    },
    "metrics": "CAGR geométrico trimestral, Sharpe anualizado sqrt(4), drawdown de NAV trimestral, ES5 de retornos trimestrales, exceso medio vs universo y número de 3 ventanas con exceso positivo",
    "empirical_p": "(1 + número de simulaciones con métrica >= observada)/(n_simulations+1); cola favorable para las seis métricas; sin elegir la métrica ganadora",
    "selection_risk": "PBO CSCV de 6 bloques y DSR de la familia fija de 257 pesos, usando stats_rigor; diagnóstico porque no reconstruye todas las configuraciones históricas",
    "interpretation": "cada nulo plantea una hipótesis condicional distinta; ninguna comparación retrospectiva confirma ventaja futura; no usar percentiles para optimizar pesos",
}


def spec_hash() -> str:
    return hashlib.sha256(json.dumps(SPEC, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _save(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def preregister() -> dict:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    path = OUTPUT / "preregistro.json"
    if path.exists():
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("sha256") != spec_hash() or record.get("spec") != SPEC:
            raise ValueError("El preregistro #49 ha cambiado.")
        return record
    record = {"sha256": spec_hash(), "spec": SPEC}
    _save(path, record)
    return record


def load_panels() -> tuple[list[pd.DataFrame], dict]:
    dates = cs.dates()
    if len(dates) != 57 or dates[0] != cs.FIRST or dates[-1] != cs.LAST:
        raise ValueError("El calendario congelado de #40 ha cambiado.")
    root = hr.VARIANTS[cs.SOURCE_VARIANT].cache
    manifest = root / "manifest.json"
    hashes = {str(manifest.relative_to(config.BASE_DIR)): _hash(manifest)}
    panels = []
    for date in dates:
        ranking_path, forward_path = root / f"ranking-{date}.csv", cs.WORK / f"forward-{date}.csv"
        ranking = pd.read_csv(ranking_path, index_col=0)
        forward = pd.read_csv(forward_path, index_col=0)
        eligible = ranking.loc[ranking.composite_score.notna() & (ranking.score_coverage >= .70)]
        if set(eligible.index) != set(forward.index):
            raise ValueError(f"Universo de #40 distinto en {date}.")
        frame = eligible[["composite_score", "sector", *BLOCKS]].join(forward[["retorno"]], validate="one_to_one")
        frame = frame.replace([np.inf, -np.inf], np.nan).dropna(subset=["composite_score", "retorno"])
        frame["sector"] = frame.sector.fillna("unknown")
        frame.attrs["date"] = date
        panels.append(frame)
        hashes[str(ranking_path.relative_to(config.BASE_DIR))] = _hash(ranking_path)
        hashes[str(forward_path.relative_to(config.BASE_DIR))] = _hash(forward_path)
    return panels, hashes


def _sorted_indices(frame: pd.DataFrame, score: np.ndarray, top_n: int, *, reverse: bool = False) -> np.ndarray:
    if len(frame) < top_n:
        raise ValueError("Universo menor que Top-N.")
    symbols = frame.index.to_numpy(dtype=str)
    return np.lexsort((symbols, score if reverse else -score))[:top_n]


def _weighted_scores(frame: pd.DataFrame, weights: np.ndarray) -> np.ndarray:
    values = frame[list(BLOCKS)].to_numpy(dtype=float)
    valid = np.isfinite(values)
    den = (valid * weights).sum(axis=1)
    return np.divide(np.nansum(values * weights, axis=1), den,
                     out=np.full(len(frame), np.nan), where=den > 0)


def _metrics(path: np.ndarray, universe: np.ndarray, dates: list[str],
             windows: tuple = STABILITY_WINDOWS) -> dict:
    if len(path) != len(universe) or len(path) != len(dates) or not np.isfinite(path).all() or (path <= -1).any():
        raise ValueError("Serie de retornos inválida o no alineada.")
    nav = np.concatenate([[1.0], np.cumprod(1 + path)])
    peak = np.maximum.accumulate(nav)
    std = path.std(ddof=1)
    losses = np.sort(path)[:max(1, int(np.ceil(.05 * len(path))))]
    excess = path - universe
    stable = sum(bool(any(start <= date < end for date in dates)) and
                 float(excess[[start <= date < end for date in dates]].mean()) > 0
                 for start, end in windows)
    return {"cagr": float(nav[-1] ** (4 / len(path)) - 1),
            "sharpe": float(path.mean() / std * 2) if std > 0 else 0.0,
            "max_drawdown": float((nav / peak - 1).min()),
            "es5": float(losses.mean()), "excess_mean": float(excess.mean()),
            "positive_windows": int(stable)}


def _weight_draws(rng: np.random.Generator, n: int) -> np.ndarray:
    raw = rng.uniform(-.025, .025, size=(n, 4))
    delta = raw - raw.mean(axis=1, keepdims=True)
    delta *= np.minimum(1, .025 / np.max(np.abs(delta), axis=1))[:, None]
    return np.asarray(BASE_WEIGHTS) + delta


def _sector_sample(groups: dict[str, np.ndarray], counts: dict[str, int],
                   rng: np.random.Generator) -> np.ndarray:
    return np.concatenate([rng.choice(group, counts[sector], replace=False)
                           for sector, group in groups.items() if counts[sector]])


def simulate(panels: list[pd.DataFrame], *, top_n: int, n_simulations: int, seed: int,
             windows: tuple = STABILITY_WINDOWS, n_weight_draws: int = 256) -> dict:
    """Motor reutilizable: paneles trimestrales congelados de cualquier variante."""
    if n_simulations < 100 or len(panels) < 12 or top_n < 2 or n_weight_draws < 2:
        raise ValueError("Se requieren al menos 100 simulaciones, 12 periodos y Top-N >= 2.")
    dates = [frame.attrs.get("date") for frame in panels]
    if any(not isinstance(date, str) for date in dates) or dates != sorted(set(dates)):
        raise ValueError("Los paneles necesitan fechas trimestrales únicas y ordenadas.")
    rng = np.random.default_rng(seed)
    nulls = ("random_ranking", "random_top_n", "sector_neutral_top_n", "sector_return_permutation")
    paths = {key: np.empty((n_simulations, len(panels)), dtype=float) for key in nulls}
    observed, universe, inverse = [], [], []
    for t, frame in enumerate(panels):
        if len(frame) < top_n or frame.index.has_duplicates:
            raise ValueError(f"Panel inválido en {dates[t]}.")
        returns = frame.retorno.to_numpy(dtype=float)
        scores = frame.composite_score.to_numpy(dtype=float)
        if not np.isfinite(returns).all() or not np.isfinite(scores).all():
            raise ValueError(f"Datos no finitos en {dates[t]}.")
        selected = _sorted_indices(frame, scores, top_n)
        observed.append(float(returns[selected].mean()))
        universe.append(float(returns.mean()))
        inverse.append(float(returns[_sorted_indices(frame, scores, top_n, reverse=True)].mean()))
        sectors = frame.sector.fillna("unknown").to_numpy(dtype=str)
        groups = {sector: np.flatnonzero(sectors == sector) for sector in np.unique(sectors)}
        counts = {sector: int((sectors[selected] == sector).sum()) for sector in groups}
        for sim in range(n_simulations):
            # Una permutación completa y una muestra Top-N son el mismo nulo
            # marginal, pero se generan de forma independiente para auditarlo.
            paths["random_ranking"][sim, t] = returns[rng.permutation(len(frame))[:top_n]].mean()
            paths["random_top_n"][sim, t] = returns[rng.choice(len(frame), top_n, replace=False)].mean()
            picks = _sector_sample(groups, counts, rng)
            paths["sector_neutral_top_n"][sim, t] = returns[picks].mean()
            shuffled = returns.copy()
            for group in groups.values():
                shuffled[group] = returns[rng.permutation(group)]
            paths["sector_return_permutation"][sim, t] = shuffled[selected].mean()
    observed, universe, inverse = np.asarray(observed), np.asarray(universe), np.asarray(inverse)
    observed_metrics = _metrics(observed, universe, dates, windows)
    all_rows, summaries = [], {}
    for null, matrix in paths.items():
        metrics = [_metrics(path, universe, dates, windows) for path in matrix]
        all_rows.extend({"null": null, "simulation": i, **item} for i, item in enumerate(metrics))
        summaries[null] = {"role": "diagnostic" if null == "sector_return_permutation" else "conditional_randomization",
                           "metrics": {key: {"observed": observed_metrics[key],
                                              "mean": float(np.mean([m[key] for m in metrics])),
                                              "p_empirical": (1 + sum(m[key] >= observed_metrics[key] for m in metrics)) / (n_simulations + 1),
                                              "q05": float(np.quantile([m[key] for m in metrics], .05)),
                                              "q50": float(np.quantile([m[key] for m in metrics], .50)),
                                              "q95": float(np.quantile([m[key] for m in metrics], .95))}
                                       for key in observed_metrics}}
    weights = _weight_draws(rng, n_weight_draws)
    weight_paths = []
    for weight in weights:
        weight_paths.append(np.asarray([frame.retorno.to_numpy(dtype=float)[
            _sorted_indices(frame, _weighted_scores(frame, weight), top_n)].mean() for frame in panels]))
    weight_metrics = [_metrics(path, universe, dates, windows) for path in weight_paths]
    weight_rows = [{"variant": i, **{f"weight_{name}": float(value) for name, value in zip(BLOCKS, weight)},
                    **metric} for i, (weight, metric) in enumerate(zip(weights, weight_metrics))]
    # Un rebalanceo retrasado: usar el score que se conocía en el trimestre anterior.
    lagged = []
    for prev, current in zip(panels[:-1], panels[1:]):
        common = current.index.intersection(prev.index)
        if len(common) < top_n:
            raise ValueError("No hay suficientes empresas comunes para el control de fecha.")
        frame = current.loc[common]
        scores = prev.loc[common, "composite_score"].to_numpy(dtype=float)
        lagged.append(float(frame.retorno.to_numpy(dtype=float)[_sorted_indices(frame, scores, top_n)].mean()))
    lagged = np.asarray(lagged)
    matrix = pd.DataFrame(np.column_stack([observed, *weight_paths]),
                          columns=["observed", *[f"weight_{i}" for i in range(len(weight_paths))]])
    pbo = stats_rigor.pbo_cscv(matrix, n_splits=6)
    trial_sharpes = [observed_metrics["sharpe"], *[item["sharpe"] for item in weight_metrics]]
    dsr = stats_rigor.deflated_sharpe_ratio(
        observed_metrics["sharpe"], trial_sharpes, len(observed), 4,
        skew=float(stats.skew(observed, bias=False)),
        kurtosis=float(stats.kurtosis(observed, fisher=False, bias=False)))
    return {"observed": observed_metrics, "nulls": summaries, "null_rows": all_rows,
            "observed_path": observed, "universe_path": universe, "null_paths": paths,
            "weight_rows": weight_rows, "weight_paths": weight_paths,
            "weight_summary": {"cagr_q05_q50_q95": np.quantile([x["cagr"] for x in weight_metrics], [.05, .5, .95]).tolist(),
                               "excess_positive_fraction": float(np.mean([x["excess_mean"] > 0 for x in weight_metrics]))},
            "inverse_sign": _metrics(inverse, universe, dates, windows),
            "date_lag": {"n_periods": len(lagged),
                         "observed_same_periods": _metrics(observed[1:], universe[1:], dates[1:], windows),
                         "perturbed": _metrics(lagged, universe[1:], dates[1:], windows)},
            "pbo_weight_family": pbo, "dsr_weight_family": dsr}


def analyze() -> dict:
    record = preregister()
    panels, hashes = load_panels()
    simulation = simulate(panels, top_n=SPEC["top_n"],
                          n_simulations=SPEC["n_simulations"], seed=SPEC["seed"])
    OUTPUT.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(simulation["null_rows"]).to_csv(OUTPUT / "null_distributions.csv", index=False)
    pd.DataFrame(simulation["weight_rows"]).to_csv(OUTPUT / "weight_perturbations.csv", index=False)
    pd.DataFrame({"fecha": [x.attrs["date"] for x in panels],
                  "observed": simulation["observed_path"], "universe": simulation["universe_path"]}).to_csv(
                      OUTPUT / "observed_by_quarter.csv", index=False)
    result = {"spec_sha256": record["sha256"], "code_sha256": _hash(Path(__file__)),
              "inputs_sha256": hashes, "seed": SPEC["seed"], "n_simulations": SPEC["n_simulations"],
              "observed": simulation["observed"], "nulls": simulation["nulls"],
              "weight_summary": simulation["weight_summary"],
              "inverse_sign": simulation["inverse_sign"], "date_lag": simulation["date_lag"],
              "pbo_weight_family": simulation["pbo_weight_family"],
              "dsr_weight_family": simulation["dsr_weight_family"]}
    _save(OUTPUT / "resultado.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preregister", action="store_true")
    parser.add_argument("--analyze", action="store_true")
    args = parser.parse_args()
    if args.preregister:
        print(preregister()["sha256"])
    if args.analyze:
        result = analyze()
        print(json.dumps({"observed": result["observed"],
                          "excess_p": {key: value["metrics"]["excess_mean"]["p_empirical"]
                                       for key, value in result["nulls"].items()}},
                         ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
