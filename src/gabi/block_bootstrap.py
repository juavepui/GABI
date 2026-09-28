"""STAT-7: paired circular-block uncertainty diagnostics, without new downloads."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

from . import academic_factors, config, research_lab

OUTPUT = config.BASE_DIR / "docs" / "block-bootstrap"
SPEC_SHA256 = "2dfbca638cb4cbeedcdb5bf0ad62f0e796548143c1aa6a174cb9e6c0e08a9c96"
BLOCK_LENGTHS = {252: (20, 10, 40), 12: (3, 2, 6), 4: (4, 2, 8), 2: (2, 4), 1: (2, 4)}
METRICS = ("cagr", "volatility", "sharpe", "max_drawdown", "es5")
COMPARISON_METRICS = ("excess_mean", "cagr_difference", "sharpe_difference")
LIMITATIONS = [
    "Remuestrear el pasado no genera evidencia OOS nueva ni corrige selección retrospectiva.",
    "Las fracciones bootstrap no son p-valores ni probabilidades de éxito futuro.",
    "Se conserva dependencia dentro de bloques; se rompe entre bloques. Se supone estacionariedad aproximada.",
    "Intervalos percentiles puntuales, sin corrección por multiplicidad ni garantía de cobertura nominal.",
    "Drawdown y ES son diagnósticos sensibles al orden, al horizonte y a colas no observadas.",
    "Volatilidad y Sharpe usan la convención sqrt(frecuencia), sin corregir su anualización por autocorrelación.",
]


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _integer(value, name: str, minimum: int) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)) or value < minimum:
        raise ValueError(f"{name} debe ser un entero >= {minimum}.")
    return int(value)


def _frequency(value: float) -> int:
    if isinstance(value, (bool, np.bool_)) or value not in BLOCK_LENGTHS:
        raise ValueError("Frecuencia explícita requerida: 252, 12, 4, 2 o 1 observaciones/año.")
    return int(value)


def _check_index(index: pd.Index, frequency: int) -> None:
    if not index.is_unique or not index.is_monotonic_increasing:
        raise ValueError("Las fechas deben ser únicas, consecutivas y ordenadas.")
    if isinstance(index, pd.RangeIndex) and index.step == 1:
        return  # caller explicitly supplies an already equally spaced matrix
    if not isinstance(index, pd.DatetimeIndex) or index.hasnans or index.tz is not None:
        raise ValueError("Se requiere DatetimeIndex sin zona horaria o RangeIndex consecutivo.")
    if not index.equals(index.normalize()):
        raise ValueError("Se requieren fechas sin hora.")
    if frequency == 252:
        import exchange_calendars as xcals

        calendar = xcals.get_calendar("XNYS", start=index[0], end=index[-1])
        sessions = calendar.sessions_in_range(index[0], index[-1]).tz_localize(None)
        if not index.equals(sessions):
            raise ValueError("Retornos diarios requieren todas las sesiones XNYS, sin huecos.")
    else:
        ordinals = index.to_period("M").asi8
        if not np.all(np.diff(ordinals) == 12 // frequency):
            raise ValueError("Los periodos deben ser consecutivos y de igual frecuencia, sin huecos.")


def _validate(frame: pd.DataFrame, frequency: int, block_size: int, n_boot: int, ci: float) -> np.ndarray:
    if not isinstance(frame, pd.DataFrame) or frame.empty or len(frame) < 30:
        raise ValueError("Se requieren al menos 30 observaciones completas.")
    if not frame.columns.is_unique or any(not isinstance(c, str) or not c or "/" in c for c in frame.columns):
        raise ValueError("Las series requieren nombres únicos no vacíos y sin '/'.")
    _check_index(frame.index, frequency)
    if isinstance(ci, (bool, np.bool_)) or not np.isfinite(ci) or not 0 < ci < 1:
        raise ValueError("ci debe estar entre 0 y 1.")
    _integer(n_boot, "n_boot", 100)
    _integer(block_size, "block_size", 2)
    if block_size > len(frame) // 2:
        raise ValueError("El bloque no puede superar la mitad de la muestra.")
    values = frame.to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("No se eliminan ni imputan NaN, infinitos o desalineaciones.")
    return values


def circular_indices(n: int, block_size: int, n_boot: int, rng: np.random.Generator) -> np.ndarray:
    """Same indices for every column; length 1 is available only as a test diagnostic."""
    starts = rng.integers(0, n, size=(n_boot, (n + block_size - 1) // block_size))
    return ((starts[..., None] + np.arange(block_size)) % n).reshape(n_boot, -1)[:, :n]


def _path_metrics(paths: np.ndarray, frequency: int, risk_free_rate: float) -> dict[str, np.ndarray]:
    """Rows are paths; ES matches the existing fractional empirical tail definition."""
    n = paths.shape[1]
    period_rf = np.expm1(np.log1p(risk_free_rate) / frequency)
    with np.errstate(divide="ignore"):
        log_nav = np.cumsum(np.log1p(paths), axis=1)
    log_peak = np.maximum.accumulate(np.maximum(log_nav, 0), axis=1)
    cagr = np.expm1(log_nav[:, -1] * frequency / n)
    vol = paths.std(axis=1, ddof=1)
    # A constant return series has no estimable Sharpe, not an artificial zero.
    sharpe = np.divide(paths.mean(axis=1) - period_rf, vol,
                       out=np.full(len(paths), np.nan), where=np.ptp(paths, axis=1) > 0)
    losses = np.sort(-paths, axis=1)[:, ::-1]
    mass = n * .05
    if abs(mass - round(mass)) < 1e-12:
        mass = float(round(mass))
    whole = int(np.floor(mass))
    es = losses[:, :whole].sum(axis=1) / mass
    if mass > whole:
        es += losses[:, whole] * ((mass - whole) / mass)
    return {"cagr": cagr, "volatility": vol * np.sqrt(frequency),
            "sharpe": sharpe * np.sqrt(frequency),
            "max_drawdown": np.expm1(log_nav - log_peak).min(axis=1), "es5": es}


def _summary(observed: float, values: np.ndarray, ci: float) -> dict:
    finite = values[np.isfinite(values)]
    alpha = (1 - ci) / 2
    result = {"observed": float(observed) if np.isfinite(observed) else None,
              "valid_draws": len(finite), "undefined_draws": len(values) - len(finite)}
    if len(finite):
        low, median, high = np.quantile(finite, [alpha, .5, 1 - alpha])
        result.update(lower=float(low), median=float(median), upper=float(high), bootstrap_mean=float(finite.mean()))
    else:
        result.update(lower=None, median=None, upper=None, bootstrap_mean=None)
    return result


def _fraction(values: np.ndarray, *, threshold: float = 0, below: bool = False) -> dict:
    finite = values[np.isfinite(values)]
    return {"fraction": float(np.mean(finite <= threshold if below else finite > threshold)) if len(finite) else None,
            "valid_draws": len(finite), "undefined_draws": len(values) - len(finite)}


def _hac_comparison(values: np.ndarray, summary: dict, ci: float) -> dict:
    fit = academic_factors._ols(values, np.ones((len(values), 1)), ["mean"])
    estimate, se = fit["coef"]["mean"], fit["se"]["mean"]
    margin = float(norm.ppf((1 + ci) / 2) * se)
    low, high = estimate - margin, estimate + margin
    boot_excludes = summary["lower"] > 0 or summary["upper"] < 0
    hac_excludes = low > 0 or high < 0
    t = fit["t_stat"]["mean"]
    return {"mean": estimate, "se": se, "lower": low, "upper": high,
            "t_hac": float(t) if np.isfinite(t) else None, "hac_lags": fit["hac_lags"],
            "bootstrap_excludes_zero": bool(boot_excludes), "hac_excludes_zero": bool(hac_excludes),
            "zero_conclusion_differs": bool(boot_excludes != hac_excludes),
            "method": "existing Newey-West/Bartlett, small-sample correction, normal interval"}


def _metadata(frame: pd.DataFrame, frequency: int, block_size: int, n_boot: int, ci: float, seed: int) -> dict:
    fingerprint = hashlib.sha256(frame.to_csv(float_format="%.17g", lineterminator="\n").encode()).hexdigest()
    return {"schema_version": 1, "method": "paired circular block bootstrap", "n_obs": len(frame),
            "start": str(frame.index[0]), "end": str(frame.index[-1]), "periods_per_year": frequency,
            "block_size": block_size, "n_boot": n_boot, "ci": ci, "seed": seed,
            "input_sha256": fingerprint, "limitations": LIMITATIONS,
            "code_sha256": {p.name: _hash(p) for p in (Path(__file__), Path(academic_factors.__file__))}}


def analyze_returns(returns: pd.DataFrame, *, periods_per_year: float, block_size: int,
                    strategy: str | None = None, n_boot: int = 4096, seed: int = 500050,
                    ci: float = .95, risk_free_rate: float = 0, drawdown_threshold: float = .2) -> tuple[dict, pd.DataFrame]:
    """Percentile uncertainty of aligned return paths, paired benchmark differences and HAC means.

    Datetime daily data must contain all XNYS sessions. RangeIndex is an explicit
    equally spaced input contract. No rows are dropped or filled. Frequencies
    and actual period windows must be checked by the caller before aggregation.
    Returned draws retain undefined Sharpes as NaN, with counts in the summary.
    """
    frequency = _frequency(periods_per_year)
    values = _validate(returns, frequency, block_size, n_boot, ci)
    seed = _integer(seed, "seed", 0)
    if not np.isfinite(risk_free_rate) or risk_free_rate <= -1:
        raise ValueError("Tipo libre de riesgo anual finito y mayor que -1 requerido.")
    if not np.isfinite(drawdown_threshold) or not 0 < drawdown_threshold <= 1:
        raise ValueError("Umbral de drawdown requerido en (0, 1].")
    if (values < -1).any():
        raise ValueError("Un retorno simple no puede ser menor que -100 %.")
    if strategy is not None and strategy not in returns:
        raise ValueError("La estrategia debe existir en la matriz de retornos.")
    observed = {name: _path_metrics(values[:, i][None, :], frequency, risk_free_rate)
                for i, name in enumerate(returns.columns)}
    chunks: dict[str, list[np.ndarray]] = {f"{name}/{metric}": [] for name in returns for metric in METRICS}
    comparisons = [name for name in returns if strategy is not None and name != strategy]
    for name in comparisons:
        for metric in COMPARISON_METRICS:
            chunks[f"vs_{name}/{metric}"] = []
    rng = np.random.default_rng(seed)
    for start in range(0, n_boot, 128):
        indices = circular_indices(len(values), block_size, min(128, n_boot - start), rng)
        batch_metrics = {}
        for i, name in enumerate(returns.columns):
            path_metrics = _path_metrics(values[indices, i], frequency, risk_free_rate)
            batch_metrics[name] = path_metrics
            for metric, array in path_metrics.items():
                chunks[f"{name}/{metric}"].append(array)
        if strategy is not None:
            strategy_i = returns.columns.get_loc(strategy)
            for name in comparisons:
                benchmark_i = returns.columns.get_loc(name)
                chunks[f"vs_{name}/excess_mean"].append((values[indices, strategy_i] - values[indices, benchmark_i]).mean(axis=1))
                for metric in ("cagr", "sharpe"):
                    chunks[f"vs_{name}/{metric}_difference"].append(batch_metrics[strategy][metric] - batch_metrics[name][metric])
    draws = pd.DataFrame({key: np.concatenate(parts) for key, parts in chunks.items()})
    if np.isinf(draws.to_numpy()).any():
        raise ValueError("Métricas no finitas; revisa las magnitudes de los retornos.")
    result = _metadata(returns, frequency, block_size, n_boot, ci, seed)
    result.update(risk_free_rate=risk_free_rate, drawdown_threshold=drawdown_threshold,
                  strategy=strategy, series={}, comparisons={})
    for name in returns:
        result["series"][name] = {
            "metrics": {metric: _summary(observed[name][metric][0], draws[f"{name}/{metric}"].to_numpy(), ci) for metric in METRICS},
            "drawdown_fraction": _fraction(draws[f"{name}/max_drawdown"].to_numpy(), threshold=-drawdown_threshold, below=True),
            "tail_mass": len(values) * .05, "tail_horizon": "one original observation", "tail_sparse": len(values) * .05 < 5,
        }
    for name in comparisons:
        observed_diff = {"excess_mean": float((returns[strategy] - returns[name]).mean()),
                         "cagr_difference": observed[strategy]["cagr"][0] - observed[name]["cagr"][0],
                         "sharpe_difference": observed[strategy]["sharpe"][0] - observed[name]["sharpe"][0]}
        metrics = {metric: _summary(observed_diff[metric], draws[f"vs_{name}/{metric}"].to_numpy(), ci) for metric in COMPARISON_METRICS}
        result["comparisons"][name] = {"metrics": metrics,
            "positive_fractions": {metric: _fraction(draws[f"vs_{name}/{metric}"].to_numpy()) for metric in COMPARISON_METRICS},
            "hac": _hac_comparison((returns[strategy] - returns[name]).to_numpy(), metrics["excess_mean"], ci)}
    return result, draws


def analyze_means(panel: pd.DataFrame, *, periods_per_year: float, block_size: int,
                  n_boot: int = 4096, seed: int = 500050, ci: float = .95) -> tuple[dict, pd.DataFrame]:
    """Temporal means of already aggregated IC/spreads; never bootstrap firms as independent dates."""
    frequency = _frequency(periods_per_year)
    values = _validate(panel, frequency, block_size, n_boot, ci)
    seed = _integer(seed, "seed", 0)
    rng = np.random.default_rng(seed)
    chunks = []
    for start in range(0, n_boot, 128):
        indices = circular_indices(len(values), block_size, min(128, n_boot - start), rng)
        chunks.append(values[indices].mean(axis=1))
    draws = pd.DataFrame(np.concatenate(chunks), columns=panel.columns)
    result = _metadata(panel, frequency, block_size, n_boot, ci, seed)
    result["means"] = {}
    for name in panel:
        summary = _summary(float(panel[name].mean()), draws[name].to_numpy(), ci)
        result["means"][name] = {"summary": summary,
                                "positive_fraction": _fraction(draws[name].to_numpy()),
                                "hac": _hac_comparison(panel[name].to_numpy(), summary, ci)}
    return result, draws


def analyze_sensitivity(frame: pd.DataFrame, *, periods_per_year: float,
                        means: bool = False, **kwargs) -> tuple[dict, pd.DataFrame]:
    """The fixed primary block and every preregistered sensitivity, never select a winner."""
    frequency = _frequency(periods_per_year)
    analyze = analyze_means if means else analyze_returns
    runs, draws = {}, []
    for block in BLOCK_LENGTHS[frequency]:
        result, distribution = analyze(frame, periods_per_year=frequency, block_size=block, **kwargs)
        runs[str(block)] = result
        distribution.insert(0, "replicate", np.arange(len(distribution)))
        distribution.insert(0, "block_size", block)
        draws.append(distribution)
    return {"primary_block": BLOCK_LENGTHS[frequency][0], "runs": runs}, pd.concat(draws, ignore_index=True)


def interval_table(audit: dict) -> pd.DataFrame:
    rows: list[dict] = []
    for block, run in audit["runs"].items():
        for name, series in run.get("series", {}).items():
            rows.extend({"block_size": int(block), "series": name, "metric": metric, **summary}
                        for metric, summary in series["metrics"].items())
        for name, comparison in run.get("comparisons", {}).items():
            rows.extend({"block_size": int(block), "series": f"vs_{name}", "metric": metric, **summary}
                        for metric, summary in comparison["metrics"].items())
        for name, mean in run.get("means", {}).items():
            rows.append({"block_size": int(block), "series": name, "metric": "mean", **mean["summary"]})
    return pd.DataFrame(rows)


def _save(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def analyze_saved() -> dict:
    """Read only previously published paths and persist an audit; does not rerun a backtest."""
    spec_path = OUTPUT / "preregistro.json"
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    digest = hashlib.sha256(json.dumps(spec, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    if digest != SPEC_SHA256 or spec["block_lengths"] != {str(k): list(v) for k, v in BLOCK_LENGTHS.items()}:
        raise ValueError("El preregistro #50 ha cambiado.")
    paths = {key: config.BASE_DIR / spec[key] for key in ("daily_nav", "daily_periods", "quarterly_returns", "cross_section")}
    hashes = {str(p.relative_to(config.BASE_DIR)): _hash(p) for p in paths.values()}
    periods = pd.read_csv(paths["daily_periods"])
    nav = pd.read_csv(paths["daily_nav"], index_col=0, parse_dates=True, float_precision="round_trip")
    if nav.isna().any().any() or (nav <= 0).any().any():
        raise ValueError("NAV guardado inválido.")
    _check_index(nav.index, 252)
    daily = nav.pct_change(fill_method=None).loc[pd.Timestamp(periods.fecha.iloc[0]):]
    quarterly = pd.read_csv(paths["quarterly_returns"], float_precision="round_trip")
    starts, ends = pd.to_datetime(quarterly.fecha), pd.to_datetime(quarterly.hasta)
    unavailable = {}
    if not np.all(ends.dt.to_period("M").array.asi8 - starts.dt.to_period("M").array.asi8 == 3):
        unavailable["v1_quarterly_net"] = "Las ventanas V1 no son trimestrales. No se realiza inferencia temporal."
    elif not np.array_equal(ends.dt.to_period("M").array.asi8[:-1], starts.dt.to_period("M").array.asi8[1:]):
        unavailable["v1_quarterly_net"] = "Las ventanas V1 tienen huecos o solapamientos. No se unen periodos separados ni se imputan retornos."
    quarterly.index = pd.DatetimeIndex(starts)
    quarterly = quarterly[list(spec["quarterly_columns"])].rename(columns=spec["quarterly_columns"])
    panel = pd.read_csv(paths["cross_section"], index_col="fecha", parse_dates=True, float_precision="round_trip")[spec["mean_columns"]]
    settings = {key: spec[key] for key in ("n_boot", "seed", "ci")}
    financial = {key: spec[key] for key in ("risk_free_rate", "drawdown_threshold")}
    report: dict = {"spec_sha256": digest, "inputs_sha256": hashes, "git_commit": research_lab._current_git_commit(),
              "dependencies": research_lab._dependency_versions(), "environment_sha256": research_lab._env_fingerprint(),
              "unavailable_datasets": unavailable, "datasets": {}}
    datasets = [("v2_daily_net", daily, 252, False), ("cross_section_means", panel, 4, True)]
    if "v1_quarterly_net" not in unavailable:
        datasets.append(("v1_quarterly_net", quarterly, 4, False))
    for name, frame, frequency, means in datasets:
        audit, distribution = analyze_sensitivity(frame, periods_per_year=frequency, means=means,
                                                  **settings, **({} if means else {"strategy": "strategy", **financial}))
        report["datasets"][name] = audit
        distribution.to_csv(OUTPUT / f"{name}-distributions.csv", index=False, lineterminator="\n")
        interval_table(audit).to_csv(OUTPUT / f"{name}-intervals.csv", index=False, lineterminator="\n")
    if hashes != {str(p.relative_to(config.BASE_DIR)): _hash(p) for p in paths.values()}:
        raise ValueError("Las entradas han cambiado durante el análisis.")
    report["artifacts_sha256"] = {f"{name}-distributions.csv": _hash(OUTPUT / f"{name}-distributions.csv")
                                for name in report["datasets"]}
    _save(OUTPUT / "resultado.json", report)
    return report


def load_saved() -> dict:
    result = json.loads((OUTPUT / "resultado.json").read_text(encoding="utf-8"))
    for name, digest in result["artifacts_sha256"].items():
        if _hash(OUTPUT / name) != digest:
            raise ValueError(f"La distribución guardada ha cambiado: {name}.")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analyze", action="store_true", help="Usar solo artefactos guardados y el preregistro #50")
    args = parser.parse_args()
    if args.analyze:
        result = analyze_saved()
        print(json.dumps({name: audit["primary_block"] for name, audit in result["datasets"].items()}, indent=2))


if __name__ == "__main__":
    main()
