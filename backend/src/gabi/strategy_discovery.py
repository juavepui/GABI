"""Three frozen retrospective candidates; diagnostics cannot certify an investment edge.

Read-only inputs. Each quarter is an independent, fully funded holding period,
not a continuous NAV. No reserved #43/#44 data or operational database is used.
"""

import argparse
import json
import sqlite3
from pathlib import Path

import exchange_calendars as xcals
import numpy as np
import pandas as pd
import scipy
from scipy import stats

from . import config
from . import factor_sector_stability as frozen

OUTPUT = config.BASE_DIR / "docs" / "strategy-discovery"
RANKINGS = config.BASE_DIR / "data" / "revalidation_2011_2025" / "acreditado-38"
SIC_SHA256 = "1f48950f7215a23e4d3fe3a05ed051c5d203b480adb6a2857da96c17de69da2d"
MODELS = {"QV": ("value", "quality"), "QVM": ("value", "quality", "momentum"),
          "QE": ("quality", "expectations")}
COSTS = {"base": 10, "stress": 25}
SPEC: dict = {
    "version": 1, "stage": "RESEARCH_RETROSPECTIVE", "demonstrated": False,
    "models": {key: list(value) for key, value in MODELS.items()},
    "value": {"metrics": ["pe", "pb", "ev_ebitda"], "positive_only": True, "minimum": 2},
    "quality": {"metrics": ["roic_persistence_mean", "operating_margin_persistence_mean", "fcf_positive_fraction"],
                "minimum": 2, "minimum_annual_observations": 3},
    "momentum": {"metrics": ["momentum_12m", "rel_strength_6m", "price_vs_sma200"], "minimum": 2},
    "expectations": {"metric": "historical_fcf_cagr-implied_fcf_growth", "discount_rate": .09,
                     "terminal_growth": .025, "forecast_years": 5},
    "scores": "equal means of available oriented percentiles; all model blocks required; no imputation",
    "percentiles": {"sector": "dated SIC division", "minimum_sector_observations": 8,
                    "fallback": "global eligible finite observations", "ties": "average"},
    "portfolio": {"slots": 20, "maximum_per_division": 6, "empty_slots": "zero-interest cash",
                  "ties": "score descending, symbol ascending", "missing_selected_return": "invalidate period"},
    "costs": {"bps_per_side": COSTS, "commission_per_trade_usd": 1, "initial_capital_usd": 100000,
              "funding": "each slot funds purchase plus both commissions; exit commission reserved in cash",
              "round_trip": "every independent period; SPY has one funded position"},
    "ic": {"minimum_pairs": 30, "minimum_quarters": 30, "hac_bartlett_lags": 3,
           "alternative": "positive mean", "multiplicity": "Holm exactly 3", "alpha": .05},
    "bootstrap": {"blocks": 4, "replicas": 5000, "seed": 20260928,
                  "lower_tail": .05 / 3, "resampling": "joint circular calendar blocks across models and costs",
                  "missing": "no bound for a column with any missing quarter; never compress calendar"},
    "windows": {name: list(bounds) for name, bounds in frozen.WINDOWS.items()},
    "daily_audit_gate": "positive Holm IC; positive excess in all windows; positive family lower bound in both costs; >=30 periods and >=8 per window",
    "inputs": {"original_result": frozen.ORIGINAL_SHA256, "sic_result": SIC_SHA256,
               "snapshot": "hash recorded in frozen original manifest; SQLite read-only"},
    "preservation": "#43/#44 and all original models, rankings and evidence are untouched",
}
ARTIFACTS = {"scores.csv", "decisions.csv", "quarterly.csv", "benchmark_periods.csv"}


def save_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def preregister() -> dict:
    record = {"spec": SPEC, "sha256": frozen.fingerprint(SPEC),
              "code_sha256": frozen.file_hash(Path(__file__), text=True),
              "protocol_sha256": frozen.file_hash(OUTPUT / "PROTOCOLO.md", text=True)}
    path = OUTPUT / "preregistro.json"
    if path.exists():
        if json.loads(path.read_text(encoding="utf-8")) != record:
            raise ValueError("El protocolo de descubrimiento ha cambiado.")
    else:
        save_json(path, record)
    return record


def numeric(frame: pd.DataFrame, name: str) -> pd.Series:
    if name not in frame:
        return pd.Series(np.nan, index=frame.index, dtype=float)
    return pd.to_numeric(frame[name], errors="coerce").replace([np.inf, -np.inf], np.nan)


def percentile(values: pd.Series, division: pd.Series, *, lower: bool = False) -> tuple[pd.Series, pd.Series]:
    values = values.replace([np.inf, -np.inf], np.nan)
    global_rank = values.rank(pct=True, ascending=not lower, method="average")
    ranked = global_rank.copy()
    fallback = values.notna().copy()
    for _, members in division.dropna().groupby(division.dropna()).groups.items():
        valid = values.loc[members].dropna()
        if len(valid) >= 8:
            ranked.loc[valid.index] = valid.rank(pct=True, ascending=not lower, method="average")
            fallback.loc[valid.index] = False
    return ranked, fallback


def score_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Scoring accesses only historical features and SIC, never future returns."""
    if frame.index.has_duplicates or frame.division.isna().any() or not frame.division.isin(frozen.DIVISION_NAMES).all():
        raise ValueError("Identidad/división SIC incompleta o duplicada.")
    result = frame[["entity_id", "division"]].copy()
    groups: dict[str, list[str]] = {key: [] for key in ("value", "quality", "momentum", "expectations")}

    def add(block: str, name: str, values: pd.Series, lower: bool = False) -> None:
        column = name + "_pct"
        result[column], result[name + "_global_fallback"] = percentile(values, frame.division, lower=lower)
        groups[block].append(column)

    for name in SPEC["value"]["metrics"]:
        values = numeric(frame, name)
        add("value", name, values.where(values > 0), lower=True)
    for metric, years in (("roic_persistence_mean", "roic_years"),
                          ("operating_margin_persistence_mean", "operating_margin_years")):
        add("quality", metric, numeric(frame, metric).where(numeric(frame, years) >= 3))
    years, positive = numeric(frame, "fcf_years"), numeric(frame, "fcf_positive_years")
    fraction = (positive / years).where((years >= 3) & (positive >= 0) & (positive <= years))
    add("quality", "fcf_positive_fraction", fraction)
    for name in SPEC["momentum"]["metrics"]:
        add("momentum", name, numeric(frame, name))
    gap = numeric(frame, "historical_fcf_cagr") - numeric(frame, "implied_fcf_growth")
    for column, expected in (("expectations_discount_rate", .09), ("expectations_terminal_growth", .025),
                             ("expectations_forecast_years", 5)):
        if not np.isclose(numeric(frame, column).loc[gap.notna()], expected).all():
            raise ValueError("Los parámetros reverse DCF no coinciden con el diseño congelado.")
    add("expectations", "expectations_gap", gap)
    for block, columns in groups.items():
        minimum = 1 if block == "expectations" else 2
        result[block + "_available"] = result[columns].notna().sum(axis=1)
        result[block] = result[columns].mean(axis=1).where(result[block + "_available"] >= minimum)
    for model, blocks in MODELS.items():
        result[model] = result[list(blocks)].mean(axis=1).where(result[list(blocks)].notna().all(axis=1))
    return result


def decisions(scores: pd.DataFrame, model: str) -> pd.DataFrame:
    """Every eligible issuer gets a decision, including omissions and cap exclusions."""
    ordered = scores.rename_axis(None).assign(symbol=scores.index).sort_values([model, "symbol"], ascending=[False, True])
    counts: dict[str, int] = {}
    selected = 0
    rows = []
    for symbol, row in ordered.iterrows():
        division = str(row.division)
        if not np.isfinite(row[model]):
            reason = "missing_blocks"
        elif selected >= 20:
            reason = "below_top20"
        elif counts.get(division, 0) >= 6:
            reason = "division_cap"
        else:
            reason = "selected"
            selected += 1
            counts[division] = counts.get(division, 0) + 1
        rows.append({"symbol": str(symbol), "entity_id": row.entity_id, "model": model,
                     "division": division, "score": row[model], "reason": reason,
                     "slot": selected if reason == "selected" else None,
                     "budget_weight": .05 if reason == "selected" else 0.0})
    return pd.DataFrame(rows)


def funded_return(returns: np.ndarray, bps: int, *, slots: int = 20) -> float | None:
    """Reserve both commissions; no debt even after a total loss. Empty slots are cash."""
    if len(returns) > slots or slots < 1 or bps < 0:
        raise ValueError("Cartera/costes inválidos.")
    if not np.isfinite(returns).all() or (returns < -1).any():
        return None
    capital = float(SPEC["costs"]["initial_capital_usd"])
    commission = float(SPEC["costs"]["commission_per_trade_usd"])
    slot_budget = capital / slots
    side = bps / 10000
    notional = (slot_budget - 2 * commission) / (1 + side)
    # One dollar per position remains as cash until the exit fee is paid.
    terminal = notional * (1 + returns) * (1 - side)
    return float((terminal.sum() + (slots - len(returns)) * slot_budget) / capital - 1)


def ic_test(values: pd.Series) -> dict:
    array = values.to_numpy(dtype=float)
    observed = np.isfinite(array)
    n = int(observed.sum())
    mean = float(array[observed].mean()) if n else None
    result: dict = {"n": n, "mean": mean, "se_hac": None, "p": 1.0, "status": "insufficient"}
    if n < 30:
        return result
    assert mean is not None
    residual = np.where(observed, array - mean, 0.0)
    meat = float(residual @ residual)
    for lag in range(1, 4):
        meat += 2 * (1 - lag / 4) * float(residual[lag:] @ residual[:-lag])
    se = float(np.sqrt(max(n / (n - 1) * meat / n**2, 0)))
    if se > 0:
        result.update(se_hac=se, p=float(stats.t.sf(float(mean) / se, df=n - 1)), status="estimable")
    else:
        result["status"] = "degenerate_hac"
    return result


def holm_three(tests: dict) -> None:
    if set(tests) != set(MODELS):
        raise ValueError("La familia debe contener exactamente QV, QVM y QE.")
    running = 0.0
    for rank, model in enumerate(sorted(tests, key=lambda key: tests[key]["p"])):
        running = max(running, min(1., (3 - rank) * tests[model]["p"]))
        tests[model]["p_holm"] = running


def bootstrap_bounds(excess: pd.DataFrame) -> dict[str, float | None]:
    """Shared resamples of the full calendar; missing selected returns block inference."""
    settings = SPEC["bootstrap"]
    n = len(excess)
    bounds: dict[str, float | None] = dict.fromkeys(excess.columns, None)
    if n < 30:
        return bounds
    rng = np.random.default_rng(settings["seed"])
    starts = rng.integers(0, n, size=(settings["replicas"], int(np.ceil(n / settings["blocks"]))))
    indices = ((starts[:, :, None] + np.arange(settings["blocks"])) % n).reshape(settings["replicas"], -1)[:, :n]
    for column in excess:
        array = excess[column].to_numpy(dtype=float)
        if np.isfinite(array).all():
            bounds[column] = float(np.quantile(array[indices].mean(axis=1), settings["lower_tail"]))
    return bounds


def benchmark(dates: list[str]) -> tuple[pd.DataFrame, str]:
    manifest = json.loads((RANKINGS / "manifest.json").read_text(encoding="utf-8"))
    snapshot = RANKINGS / "snapshot.db"
    expected = manifest["snapshot_sha256"]
    if frozen.file_hash(snapshot) != expected:
        raise ValueError("El snapshot de precios no coincide con el manifest congelado.")
    with sqlite3.connect(snapshot.resolve().as_uri() + "?mode=ro", uri=True) as connection:
        prices = pd.read_sql_query("SELECT date, adj_close FROM prices WHERE symbol = 'SPY' ORDER BY date", connection)
    if prices.date.duplicated().any():
        raise ValueError("Precios SPY duplicados.")
    prices = prices.set_index("date").adj_close
    calendar = xcals.get_calendar("XNYS")
    rows = []
    for date in dates:
        signal = calendar.date_to_session(pd.Timestamp(date), direction="previous")
        entry = calendar.next_session(signal).strftime("%Y-%m-%d")
        exit_date = calendar.date_to_session(pd.Timestamp(date) + pd.DateOffset(months=3), direction="next").strftime("%Y-%m-%d")
        pair = prices.reindex([entry, exit_date]).to_numpy(dtype=float)
        if not np.isfinite(pair).all() or (pair <= 0).any():
            raise ValueError(f"Falta precio ajustado SPY exacto: {date}, {entry}, {exit_date}")
        gross = float(pair[1] / pair[0] - 1)
        rows.append({"fecha": date, "entry": entry, "exit": exit_date, "entry_adj_close": pair[0],
                     "exit_adj_close": pair[1], "spy_gross": gross,
                     **{f"spy_{cost}": funded_return(np.array([gross]), bps, slots=1) for cost, bps in COSTS.items()}})
    return pd.DataFrame(rows).set_index("fecha"), expected


def inputs() -> tuple[dict[str, pd.DataFrame], dict]:
    frames, fingerprints = frozen.frozen_frames()  # verifies all original hashes before score/return use
    sector = frozen.load_saved(SIC_SHA256)
    assigned = pd.read_csv(frozen.OUTPUT / "assignments.csv", dtype=str, keep_default_na=False)
    if assigned.duplicated(["fecha", "symbol"]).any():
        raise ValueError("Asignaciones SIC duplicadas.")
    for date, frame in frames.items():
        original = pd.read_csv(RANKINGS / f"ranking-{date}.csv", index_col=0)
        raw = original.loc[frame.index].copy()
        labels = assigned.loc[assigned.fecha == date].set_index("symbol")
        if set(labels.index) != set(frame.index) or not labels.entity_id.reindex(frame.index).equals(frame.entity_id):
            raise ValueError(f"Universo/identidad SIC distinto: {date}")
        raw["division"] = labels.division
        raw["retorno"] = frame.retorno
        frames[date] = raw
    return frames, {"original_files": fingerprints, "sic_artifacts": sector["artifacts_sha256"],
                    "original_result": frozen.ORIGINAL_SHA256, "sic_result": SIC_SHA256}


def summarize(panel: pd.DataFrame) -> dict:
    tests = {model: ic_test(panel.loc[panel.model == model, "ic"]) for model in MODELS}
    holm_three(tests)
    dates = sorted(panel.fecha.unique())
    excess = pd.DataFrame(index=dates)
    for model in MODELS:
        part = panel.loc[panel.model == model].set_index("fecha").reindex(dates)
        for cost in COSTS:
            excess[f"{model}_{cost}"] = part[f"excess_{cost}"]
    bounds = bootstrap_bounds(excess)
    result = {}
    for model in MODELS:
        part = panel.loc[panel.model == model]
        costs = {}
        failures = []
        if tests[model]["mean"] is None or tests[model]["mean"] <= 0 or tests[model]["p_holm"] >= .05:
            failures.append("ic_not_positive_after_holm")
        for cost in COSTS:
            name = f"excess_{cost}"
            valid = part.loc[np.isfinite(part[name])]
            windows = {}
            for window, (start, end) in frozen.WINDOWS.items():
                sub = valid.loc[(valid.fecha >= start) & (valid.fecha < end)]
                mean = float(sub[name].mean()) if len(sub) else None
                windows[window] = {"n": len(sub), "mean_excess": mean}
                if len(sub) < 8 or mean is None or mean <= 0:
                    failures.append(f"{cost}_{window}_insufficient_or_nonpositive")
            lower = bounds[f"{model}_{cost}"]
            if len(valid) < 30 or lower is None or lower <= 0:
                failures.append(f"{cost}_insufficient_or_lower_bound_nonpositive")
            costs[cost] = {"n": len(valid), "mean_excess": float(valid[name].mean()) if len(valid) else None,
                           "family_lower_bound": lower, "windows": windows,
                           "invalid_dates": part.loc[~np.isfinite(part[name]), "fecha"].tolist()}
        result[model] = {"ic": tests[model], "costs": costs, "audit_daily": not failures,
                         "failures": failures, "demonstrated": False,
                         "minimum_selected": int(part.n_selected.min()), "maximum_selected": int(part.n_selected.max())}
    return result


def analyze(destination: Path = OUTPUT) -> dict:
    record = preregister()
    if (destination / "resultado.json").exists():
        raise ValueError("El diagnóstico ya está congelado; no se sobrescribe.")
    frames, sources = inputs()
    spy, snapshot_hash = benchmark(list(frames))
    sources["snapshot_sha256"] = snapshot_hash
    all_scores, all_decisions, quarters = [], [], []
    for date, frame in frames.items():
        scores = score_frame(frame)
        scores.index.name = "symbol"
        all_scores.append(scores.reset_index().assign(fecha=date))
        for model in MODELS:
            chosen = decisions(scores, model)
            all_decisions.append(chosen.assign(fecha=date))
            selected = chosen.loc[chosen.reason == "selected", "symbol"]
            returns = frame.retorno.reindex(selected).to_numpy(dtype=float)
            pairs = pd.concat([scores[model], frame.retorno], axis=1).replace([np.inf, -np.inf], np.nan).dropna()
            ic = float(stats.spearmanr(pairs[model], pairs.retorno).statistic) if (
                len(pairs) >= 30 and pairs[model].nunique() > 1 and pairs.retorno.nunique() > 1) else None
            row = {"fecha": date, "model": model, "n_universe": len(frame),
                   "n_scored": int(scores[model].notna().sum()), "n_pairs": len(pairs), "ic": ic,
                   "n_selected": len(selected), "cash_budget_weight": (20 - len(selected)) / 20,
                   "missing_selected": ";".join(selected.loc[~np.isfinite(returns) | (returns < -1)].tolist())}
            for cost, bps in COSTS.items():
                value = funded_return(returns, bps)
                row[f"net_{cost}"] = value
                row[f"excess_{cost}"] = value - float(spy.loc[date, f"spy_{cost}"]) if value is not None else None
            quarters.append(row)
    panel = pd.DataFrame(quarters)
    tables = {"scores.csv": pd.concat(all_scores, ignore_index=True),
              "decisions.csv": pd.concat(all_decisions, ignore_index=True), "quarterly.csv": panel,
              "benchmark_periods.csv": spy.reset_index()}
    destination.mkdir(parents=True, exist_ok=True)
    for name, table in tables.items():
        table.to_csv(destination / name, index=False, lineterminator="\n")
    result = {"spec_sha256": record["sha256"], "protocol_sha256": record["protocol_sha256"],
              "code_sha256": frozen.file_hash(Path(__file__), text=True), "stage": SPEC["stage"],
              "demonstrated": False, "n_dates": len(frames), "n_candidates": len(MODELS),
              "inputs": sources, "models": summarize(panel),
              "versions": {"pandas": pd.__version__, "numpy": np.__version__, "scipy": scipy.__version__,
                           "exchange_calendars": xcals.__version__},
              "artifacts_sha256": {name: frozen.file_hash(destination / name, text=True) for name in tables},
              "limitations": ["history already observed; this is not independent validation",
                              "independent holding periods, no continuous CAGR or daily risk estimates",
                              "inherited non-strict/terminal equity exits require daily audit",
                              "conditioned original eligible universe, not complete historical S&P 500",
                              "family correction covers these three candidates only; prior search remains"],
              "next_step": "daily funded audit only for candidates passing every preregistered gate"}
    save_json(destination / "resultado.json", result)
    return result


def verify() -> dict:
    record = preregister()
    result = json.loads((OUTPUT / "resultado.json").read_text(encoding="utf-8"))
    if result["spec_sha256"] != record["sha256"] or result["protocol_sha256"] != record["protocol_sha256"]:
        raise ValueError("Especificación publicada modificada.")
    if result["code_sha256"] != record["code_sha256"]:
        raise ValueError("Motor publicado modificado.")
    if set(result["artifacts_sha256"]) != ARTIFACTS:
        raise ValueError("Artefactos del diagnóstico incompletos.")
    for name, expected in result["artifacts_sha256"].items():
        if frozen.file_hash(OUTPUT / name, text=True) != expected:
            raise ValueError(f"Artefacto modificado: {name}")
    frames, sources = inputs()
    spy, snapshot = benchmark(list(frames))
    sources["snapshot_sha256"] = snapshot
    if result["inputs"] != sources:
        raise ValueError("Fuentes publicadas modificadas.")
    saved_spy = pd.read_csv(OUTPUT / "benchmark_periods.csv", float_precision="round_trip").set_index("fecha")
    pd.testing.assert_frame_equal(saved_spy, spy, check_exact=False, rtol=1e-12, atol=1e-12)
    calculated = summarize(pd.read_csv(OUTPUT / "quarterly.csv", float_precision="round_trip"))
    if frozen.fingerprint(calculated) != frozen.fingerprint(result["models"]):
        raise ValueError("El resumen de modelos no reproduce el publicado.")
    if result["demonstrated"] or any(model["demonstrated"] for model in result["models"].values()):
        raise ValueError("Un diagnóstico exploratorio no puede declarar una estrategia demostrada.")
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
        print(json.dumps({"sha256": frozen.fingerprint(result), "models": result["models"],
                          "demonstrated": result["demonstrated"]}, ensure_ascii=False, indent=2))
