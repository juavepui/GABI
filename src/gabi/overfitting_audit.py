"""Reconstruct documented V1 trials and retain their common return matrix.

This is a retrospective RESEARCH audit, not a new strategy search or an
out-of-sample validation. The catalog and exclusions precede the calculation.
"""
import argparse
import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

import exchange_calendars as xcals
import numpy as np
import pandas as pd

from . import config, identity, research_lab, scoring, screener_asof, stats_rigor, universe
from . import multifactor_backtest as bt

START = "2016-07-02"
END = "2025-07-02"
SELECTED_TRIAL = "top20_q"


@dataclass(frozen=True)
class Trial:
    trial_id: str
    top_n: int = 20
    months: int = 3
    buffer_multiplier: float = 1.0
    cost_bps: float = 10.0
    sma_filter: bool = False
    role: str = "strategy"
    evidence: str = "README: Resultado corregido"

    def __post_init__(self):
        if (self.months not in (3, 6, 12) or not 1 <= self.top_n <= 50
                or not 0 <= self.cost_bps < 10000 or not np.isfinite(self.buffer_multiplier)
                or self.buffer_multiplier < 1):
            raise ValueError("Parámetros de ensayo no válidos.")


def documented_trials() -> list[Trial]:
    """Only parameter combinations explicitly recorded before this audit."""
    band_source = "README: Hipótesis descongelada, bandas 1.3/1.5/2.0 y costes 10/25/50pb"
    frequency_source = "README: Hipótesis descongelada, frecuencias trimestral/semestral/anual y costes 10/25/50pb"
    primary = [
        Trial("top10_q", top_n=10), Trial(SELECTED_TRIAL), Trial("top30_q", top_n=30),
        Trial("top10_sma200_q", top_n=10, sma_filter=True,
              evidence="README: Experimento de posiciones y filtro SMA200 del SPY, exposición 50% en bajista"),
        *[Trial(f"buffer{int(b * 10)}_q", buffer_multiplier=b, evidence=band_source) for b in (1.3, 1.5, 2.0)],
        Trial("top20_semestral", months=6, evidence=frequency_source),
        Trial("top20_anual", months=12, evidence=frequency_source),
    ]
    sensitivity = []
    for trial in primary:
        costs = (25, 50, 100) if trial.trial_id == "top10_q" else (
            (25, 50) if trial.top_n == 20 else ()
        )
        for cost in costs:
            evidence = ("README: Costes de fricción, Top-10 con 10/25/50/100pb"
                        if trial.top_n == 10 else band_source if trial.buffer_multiplier > 1 else frequency_source)
            sensitivity.append(replace(trial, trial_id=f"{trial.trial_id}_cost{cost}", cost_bps=cost,
                                       role="cost_sensitivity", evidence=evidence))
    return primary + sensitivity


EXCLUSIONS = [
    {"trial": "Tres perturbaciones de pesos", "reason": "HIPOTESIS_CONGELADA solo indica pesos parciales y solapamiento de posiciones, no vectores completos ni series."},
    {"trial": "Factores individuales vs multifactor", "reason": "Mencionado en HIPOTESIS_CONGELADA, sin especificación completa de selección/periodos/umbrales."},
    {"trial": "Versiones previas con bugs y distintas coberturas/universos", "reason": "Se reconstruyen reglas con código actual, no se recrean bugs ni se conocen todos los intentos originales."},
    {"trial": "V2, optimización de carteras y ensayos de otros rangos", "reason": "Motor/contabilidad o periodo diferentes; no se mezclan con esta familia V1."},
]


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def matrix_sha256(path: Path) -> str:
    """Canonical LF line endings make published CSV hashes portable across Git checkouts."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def prepare_rankings(cache_dir: Path, *, max_symbols: int = 200, progress=print) -> dict:
    """One expensive ranking per date, shared by all trial variants.

    A consistent SQLite backup fixes the database used for the entire audit.
    The cache is explicit and resumable; it is never mixed with a fresh DB.
    """
    cache_dir = Path(cache_dir)
    if max_symbols < 1:
        raise ValueError("max_symbols debe ser positivo.")
    cache_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = cache_dir / "manifest.json"
    source_paths = [Path(__file__).with_name(name) for name in (
        "multifactor_backtest.py", "screener_asof.py", "scoring.py", "identity.py",
        "entity_master.py", "edgar.py", "technicals.py", "risk.py", "storage.py", "config.py", "universe.py",
    )]
    source_paths += [config.DATA_DIR / name for name in (
        "sp500_historical_membership.csv", "sec_cik_map.csv",
    )]
    hashes = {str(p.relative_to(config.BASE_DIR)).replace("\\", "/"): sha256(p) for p in source_paths}
    snapshot = cache_dir / "snapshot.db"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest["max_symbols"] != max_symbols or manifest["sources_sha256"] != hashes:
            raise ValueError("La caché pertenece a otros inputs/código; usa un directorio nuevo.")
        if not snapshot.exists() or sha256(snapshot) != manifest["snapshot_sha256"]:
            raise ValueError("El snapshot de datos falta o fue alterado.")
    else:
        if snapshot.exists():
            raise ValueError("Snapshot sin manifiesto; usa un directorio nuevo.")
        with sqlite3.connect(f"file:{config.DB_PATH.as_posix()}?mode=ro", uri=True) as src:
            with sqlite3.connect(snapshot) as dest:
                src.backup(dest)
        manifest = {
            "created_at": datetime.now(UTC).isoformat(), "start": START, "end": END,
            "max_symbols": max_symbols, "seed": 42, "weights": scoring.DEFAULT_WEIGHTS,
            "snapshot_sha256": sha256(snapshot), "sources_sha256": hashes, "rankings": {},
        }
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    previous_db = config.DB_PATH
    config.DB_PATH = snapshot
    try:
        for i in range(36):
            as_of = pd.Timestamp(START) + pd.DateOffset(months=3 * i)
            date_key = as_of.date().isoformat()
            path = cache_dir / f"ranking-{date_key}.csv"
            recorded = manifest["rankings"].get(date_key)
            if recorded and path.exists() and sha256(path) == recorded["sha256"]:
                progress(f"Ranking {i + 1}/36 {date_key}: caché verificada", flush=True)
                continue
            membership = universe.get_sp500_constituents_asof(date_key)
            if not membership["is_exact"]:
                raise ValueError(membership["note"])
            symbols = bt._sample_symbols(membership["symbols"], max_symbols)
            table = screener_asof.build_ranking_as_of(date_key, symbols=symbols)["table"]
            table.to_csv(path)
            manifest["rankings"][date_key] = {"sha256": sha256(path), "symbols": symbols}
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            progress(f"Ranking {i + 1}/36 {date_key}: {len(table)} empresas", flush=True)
    finally:
        config.DB_PATH = previous_db
    return manifest


def _quarterly_marks(histories: dict, picks: list[str], as_of: pd.Timestamp, trial: Trial,
                     held: set[str], exposure: float) -> pd.Series:
    """Mark a buy-and-hold basket at actual quarterly exits, including costs.

    No interpolation of half-year/year returns. Costs apply to the same names
    as V1; uninvested cash earns zero (the documented SMA exposure rule).
    """
    calendar = xcals.get_calendar("XNYS")
    entry = calendar.next_session(calendar.date_to_session(as_of, direction="previous"))
    dates = [calendar.date_to_session(as_of + pd.DateOffset(months=m), direction="next")
             for m in range(3, trial.months + 1, 3)]
    values = []
    for symbol in picks:
        prices = histories[symbol]["adj_close"]
        quotes = prices.reindex([entry, *dates])
        if not np.isfinite(quotes).all() or (quotes <= 0).any():
            raise ValueError(f"{symbol}: faltan precios positivos en marcas trimestrales.")
        cost_factor = 1.0 if symbol in held else (1 - trial.cost_bps / 10000) ** 2
        values.append(quotes.iloc[1:].to_numpy() / quotes.iloc[0] * cost_factor)
    nav = (1 - exposure) + exposure * np.mean(values, axis=0)
    return pd.Series(nav / np.r_[1.0, nav[:-1]] - 1, index=pd.DatetimeIndex(dates))


def reconstruct_matrix(cache_dir: Path, *, trials: list[Trial] | None = None, progress=print) -> pd.DataFrame:
    """Fail on any missing trial/date: never silently drop or fill observations."""
    cache_dir = Path(cache_dir)
    manifest = json.loads((cache_dir / "manifest.json").read_text(encoding="utf-8"))
    if sha256(cache_dir / "snapshot.db") != manifest["snapshot_sha256"]:
        raise ValueError("El snapshot de datos fue alterado.")
    for name, expected in manifest["sources_sha256"].items():
        if sha256(config.BASE_DIR / name) != expected:
            raise ValueError(f"Código/input cambiado desde la reconstrucción: {name}.")
    trials = documented_trials() if trials is None else trials
    if len({t.trial_id for t in trials}) != len(trials):
        raise ValueError("Los identificadores de ensayos deben ser únicos.")
    previous: dict[str, list[str]] = {t.trial_id: [] for t in trials}
    pieces: dict[str, list[pd.Series]] = {t.trial_id: [] for t in trials}
    previous_db = config.DB_PATH
    config.DB_PATH = cache_dir / "snapshot.db"
    try:
        for i in range(36):
            as_of = pd.Timestamp(START) + pd.DateOffset(months=3 * i)
            date_key = as_of.date().isoformat()
            path = cache_dir / f"ranking-{date_key}.csv"
            if sha256(path) != manifest["rankings"][date_key]["sha256"]:
                raise ValueError(f"Ranking alterado: {date_key}.")
            ranked = pd.read_csv(path, index_col="symbol", float_precision="round_trip")
            eligible = ranked[ranked["composite_score"].notna() & (ranked["score_coverage"] >= .7)]
            if len(eligible) / len(ranked) < .5:
                raise ValueError(f"Cobertura insuficiente en {date_key}; auditoría incompleta.")
            active = [t for t in trials if (3 * i) % t.months == 0]
            selected = {}
            for trial in active:
                picks = bt._apply_holding_buffer(previous[trial.trial_id], eligible.index.tolist(),
                                                  trial.top_n, trial.buffer_multiplier)
                if len(picks) != trial.top_n:
                    raise ValueError(f"{trial.trial_id} {date_key}: faltan candidatas.")
                selected[trial.trial_id] = picks
            symbols = sorted({s for picks in selected.values() for s in picks})
            histories = identity.backtest_prices(symbols + ["SPY"], date_key)
            # Endpoint/recycled-ticker validation reuses V1 once per distinct
            # basket/holding horizon; costs do not affect data availability.
            checked = {}
            for trial in active:
                picks = selected[trial.trial_id]
                key = (tuple(picks), trial.months)
                if key not in checked:
                    checked[key] = bt._period_returns(picks, as_of, trial.months, 0.0)["portfolio_return"]
                exposure = 1.0
                if trial.sma_filter:
                    past = histories["SPY"]["adj_close"].loc[:as_of].dropna()
                    if len(past) < 200:
                        raise ValueError("Faltan 200 sesiones previas para SMA200.")
                    exposure = .5 if past.iloc[-1] < past.iloc[-200:].mean() else 1.0
                held = set(picks) & set(previous[trial.trial_id])
                marks = _quarterly_marks(histories, picks, as_of, trial, held, exposure)
                pieces[trial.trial_id].append(marks)
                previous[trial.trial_id] = picks
            progress(f"Retornos {i + 1}/36 {date_key}: {len(active)} ensayos", flush=True)
    finally:
        config.DB_PATH = previous_db
    matrix = pd.concat({name: pd.concat(parts) for name, parts in pieces.items()}, axis=1).sort_index()
    if len(matrix) != 36 or not np.isfinite(matrix.to_numpy()).all() or not matrix.index.is_unique:
        raise ValueError("La matriz no contiene 36 observaciones finitas comunes a todos los ensayos.")
    matrix.index.name = "date"
    return matrix


def analyze_matrix(matrix: pd.DataFrame, *, selected: str = SELECTED_TRIAL,
                   risk_free_rate: float = .04, n_splits: int = 6) -> dict:
    """Same quarterly arithmetic Sharpe and RF for every trial and statistic."""
    if (matrix.empty or matrix.shape[1] < 2 or selected not in matrix.columns
            or not matrix.columns.is_unique or not matrix.index.is_unique
            or not matrix.index.is_monotonic_increasing or not np.isfinite(matrix.to_numpy()).all()
            or (matrix <= -1).any().any()):
        raise ValueError("Se exige una matriz completa, ordenada, finita y con ensayos únicos.")
    if not isinstance(matrix.index, pd.DatetimeIndex) or not np.all(np.diff(matrix.index.to_period("M").asi8) == 3):
        raise ValueError("Las observaciones deben estar en una rejilla trimestral consecutiva.")
    if (matrix.std(ddof=1) <= 0).any():
        raise ValueError("Un ensayo sin varianza no tiene Sharpe definido.")
    if n_splits < 2 or n_splits % 2 or len(matrix) % n_splits:
        raise ValueError("La auditoría exige un número par de bloques de igual tamaño, sin recortar fechas.")
    if not np.isfinite(risk_free_rate) or risk_free_rate <= -1:
        raise ValueError("Tipo libre de riesgo inválido.")
    excess = matrix - ((1 + risk_free_rate) ** .25 - 1)
    moments = {name: stats_rigor.probabilistic_sharpe_ratio_from_returns(matrix[name], 4, risk_free_rate)
               for name in matrix}
    sharpes = [moments[name]["sharpe_anualizado"] for name in matrix]
    chosen = moments[selected]
    dsr_args = dict(selected_sharpe=chosen["sharpe_anualizado"], trial_sharpes=sharpes, n_obs=len(matrix),
                    periods_per_year=4, skew=chosen["skew"], kurtosis=chosen["kurtosis"])
    correlations = matrix.corr().to_numpy()
    return {
        "selected_trial": selected, "n_obs": len(matrix), "n_trials": matrix.shape[1],
        "periods_per_year": 4, "risk_free_rate": risk_free_rate, "sharpe_convention": "arithmetic excess mean / sample std",
        "trial_statistics": moments, "dsr": stats_rigor.deflated_sharpe_ratio(**dsr_args),
        "pbo": stats_rigor.pbo_cscv(excess, n_splits=n_splits), "n_splits": n_splits,
        "pbo_sensitivity": {str(s): stats_rigor.pbo_cscv(excess, n_splits=s)
                            for s in (4, 12) if s <= len(matrix) and len(matrix) % s == 0},
        "dsr_trial_count_sensitivity": {str(n): stats_rigor.deflated_sharpe_ratio(**dsr_args, n_trials=n)
                                        for n in sorted({len(matrix.columns), 12, 24, 50, 100}) if n >= len(matrix.columns)},
        "mean_pairwise_correlation": float(correlations[np.triu_indices(len(matrix.columns), k=1)].mean()),
        "limitations": ["Nominal trial count, not an estimate of independent trials.",
                        "DSR count sensitivity holds observed Sharpe variance fixed; missing trial returns are unknown.",
                        "PSR/DSR are asymptotic and do not correct serial correlation.",
                        "PBO evaluates Sharpe maximization, not the original joint Sharpe/drawdown choice.",
                        "CSCV reuses historical data; its OOS partitions are not prospective evidence."],
    }


def load_audit(output_dir: Path) -> tuple[dict, pd.DataFrame]:
    """Load the portable report and verify that its matrix has not changed."""
    output_dir = Path(output_dir)
    report = json.loads((output_dir / "audit.json").read_text(encoding="utf-8"))
    path = output_dir / "returns.csv"
    if matrix_sha256(path) != report["matrix_sha256"]:
        raise ValueError("La matriz no coincide con la huella del informe.")
    matrix = pd.read_csv(path, index_col=0, parse_dates=True, float_precision="round_trip")
    if list(matrix.columns) != [t["trial_id"] for t in report["catalog"]]:
        raise ValueError("La matriz no coincide con el catálogo del informe.")
    return report, matrix


def write_audit(matrix: pd.DataFrame, cache_dir: Path | None, output_dir: Path, *,
                register: bool = False, input_manifest: dict | None = None) -> dict:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    previous_report = None
    if (output_dir / "audit.json").exists():
        previous_report = json.loads((output_dir / "audit.json").read_text(encoding="utf-8"))
    trials = documented_trials()
    if list(matrix.columns) != [t.trial_id for t in trials]:
        raise ValueError("La matriz no coincide con el catálogo documentado.")
    matrix_path = output_dir / "returns.csv"
    if input_manifest is None:
        if cache_dir is None:
            raise ValueError("Falta el manifiesto de procedencia.")
        input_manifest = json.loads((Path(cache_dir) / "manifest.json").read_text(encoding="utf-8"))
    manifest = input_manifest
    primary = [t.trial_id for t in trials if t.role == "strategy"]
    primary_result = analyze_matrix(matrix[primary])
    all_result = analyze_matrix(matrix)
    matrix.to_csv(matrix_path, lineterminator="\n")
    report: dict = {
        "stage": "RESEARCH", "coverage": "partial_documented_V1_search",
        "created_at": datetime.now(UTC).isoformat(), "catalog": [asdict(t) for t in trials],
        "excluded": EXCLUSIONS, "inputs": manifest,
        "matrix_sha256": matrix_sha256(matrix_path), "matrix_hash_convention": "SHA256 of CSV with LF line endings",
        "code_sha256": sha256(Path(__file__)),
        "stats_code_sha256": sha256(Path(stats_rigor.__file__)),
        "primary": primary_result, "including_cost_sensitivity": all_result,
    }
    if (previous_report and previous_report.get("matrix_sha256") == report["matrix_sha256"]
            and "research_lab_ids" in previous_report):
        report["research_lab_ids"] = previous_report["research_lab_ids"]
    if register:
        ids = []
        family = f"retrospective_v1_{report['matrix_sha256'][:12]}"
        existing = research_lab.list_experiments(family=family)
        for trial in trials:
            model_id = f"audit-v1:{trial.trial_id}"
            known = existing[existing["model_id"] == model_id]
            if not known.empty:
                ids.append(int(known.iloc[0]["id"]))
                continue
            stat = report["including_cost_sensitivity"]["trial_statistics"][trial.trial_id]
            ids.append(research_lab.log_experiment(
                model_id, "RESEARCH", False, universe=f"S&P 500 histórico, muestra {manifest['max_symbols']}, semilla 42",
                factors="Value/Quality/Momentum/Risk", weights=scoring.DEFAULT_WEIGHTS,
                n_positions=trial.top_n, rebalance=f"{trial.months} meses; retornos observados trimestralmente",
                cost_model=f"V1 {trial.cost_bps:g}pb por lado", is_start=START, is_end=END, family=family,
                sharpe=stat["sharpe_anualizado"], periods_per_year=4, n_periods=len(matrix),
                returns=matrix[trial.trial_id], data_fingerprint=report["matrix_sha256"],
                notes="Auditoría retrospectiva parcial; Sharpe aritmético de excesos, RF anual 4%. Ver manifiesto y exclusiones.",
                result={"trial": asdict(trial), "matrix_sha256": report["matrix_sha256"],
                        "audit": report["primary"] if trial.trial_id == SELECTED_TRIAL else None,
                        "risk_free_rate": .04, "return_frequency": "quarterly", "exclusions": EXCLUSIONS},
            ))
        report["research_lab_ids"] = ids
    (output_dir / "audit.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, default=config.DATA_DIR / "overfitting_audit")
    parser.add_argument("--output-dir", type=Path, default=config.BASE_DIR / "docs" / "overfitting-audit")
    parser.add_argument("--max-symbols", type=int, default=200)
    parser.add_argument("--analyze-only", action="store_true", help="Recalculate statistics from the saved matrix without backtesting.")
    parser.add_argument("--register", action="store_true", help="Store all trial return series in Research Lab (idempotent per matrix).")
    args = parser.parse_args()
    manifest = None
    if args.analyze_only:
        old_report, matrix = load_audit(args.output_dir)
        manifest = old_report["inputs"]
    else:
        prepare_rankings(args.cache_dir, max_symbols=args.max_symbols)
        matrix = reconstruct_matrix(args.cache_dir)
    report = write_audit(matrix, args.cache_dir, args.output_dir, register=args.register, input_manifest=manifest)
    print(json.dumps({"n_trials": report["primary"]["n_trials"], "dsr": report["primary"]["dsr"],
                      "pbo": report["primary"]["pbo"]["pbo"], "all_trials": report["including_cost_sensitivity"]["n_trials"]}, indent=2))


if __name__ == "__main__":
    main()
