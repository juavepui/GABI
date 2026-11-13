"""One preregistered cash-conversion/repurchase hypothesis on observed history.

All source engines remain frozen. Issuer cash-flow ratios avoid unaudited
share-class market capitalisation and split-adjusted share counts.
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from . import capital_input_audit_v2 as audit
from . import strategy_discovery as parent

frozen = parent.frozen
OUTPUT = parent.OUTPUT / "repurchase-cash-v1"
AUDIT_SHA256 = "a75cb5d24429d44a8696155a839c30d61ef22ecb4c0b420abd1b716e9b1e419e"
PARENT_SHA256 = "2eeeb8298a30d15d61fc36e63ba353d94147bbb3280f0a61babdac23c4332e35"
AUDIT_CODE_SHA256 = "fc3d8da588aab1694440eebb2fd50ff8e8ad4389e6ca0e71147dceb9fdfecd87"
MODEL = "RCF"
SEARCH_COUNT_LOWER_BOUND = 34
ALPHA = .05 / SEARCH_COUNT_LOWER_BOUND
SPEC: dict = {
    "version": 1, "stage": "RESEARCH_RETROSPECTIVE", "demonstrated": False,
    "model": MODEL, "new_configurations": 1,
    "hypothesis": "cash-converting nonfinancial issuers allocating a higher fraction of positive FCF to gross common repurchases may outperform SPY",
    "eligibility": "current admitted annual filing; buybacks/OCF/capex reported for identical annual start/end/accession; OCF>0; FCF=OCF-capex>0; 0<buybacks<=FCF; exclude SIC H",
    "normalization": {"repurchase_fraction": "gross common repurchases / positive matched FCF",
                      "cash_conversion": "matched FCF / positive matched OCF"},
    "interpretation": "cash allocation ratios, not valuation yields, net payout, net share retirement or proof of debt-free funding",
    "identity": "one security per dated CIK; alphabetical ticker before eligibility, score or return; no replacement if its return is missing",
    "score": "equal mean of two higher-is-better percentiles on eligible unique issuers",
    "percentiles": parent.SPEC["percentiles"], "portfolio": parent.SPEC["portfolio"],
    "costs": parent.SPEC["costs"],
    "calendar": "57 frozen independent holding periods, exact same sessions as parent SPY; no continuous CAGR",
    "ic": {"minimum_pairs": 30, "minimum_quarters": 30, "hac_bartlett_lags": 3,
           "alternative": "positive mean", "alpha": ALPHA},
    "bootstrap": {"replicas": 5000, "blocks": 4, "seed": 20260929, "lower_tail": ALPHA,
                  "resampling": "joint circular full-calendar blocks across both costs",
                  "missing": "any missing quarter prevents bound; never compress calendar"},
    "multiplicity": {"new_family_size": 1, "search_count_lower_bound": SEARCH_COUNT_LOWER_BOUND,
                     "decision_guard": "Bonferroni over known lower bound of 34 configurations; incomplete prior ledger, no global error-control claim"},
    "windows": {key: list(value) for key, value in frozen.WINDOWS.items()},
    "daily_gate": "positive IC with p<alpha; >=30 eligible issuers on >=30 dates and >=8 per window; positive mean SPY excess in every window; positive lower bound for both costs, >=30 valid periods and >=8 per window",
    "secondary_control": "funded equal-weight all eligible unique issuers, same costs; descriptive only, no additional candidate or hypothesis test",
    "inputs": {"audit_result": AUDIT_SHA256, "audit_code": AUDIT_CODE_SHA256,
               "parent_code": PARENT_SHA256, "original_result": frozen.ORIGINAL_SHA256,
               "sic_result": parent.SIC_SHA256},
    "preservation": "frozen originals, operational DB, Investor, #43/#44 and #53 untouched",
}
ARTIFACTS = parent.ARTIFACTS | {"coverage.csv"}


def dependencies() -> None:
    for module, expected in ((parent, PARENT_SHA256), (audit, AUDIT_CODE_SHA256)):
        assert module.__file__ is not None
        if frozen.file_hash(Path(module.__file__), text=True) != expected:
            raise ValueError("Motor dependiente modificado.")


def preregister() -> dict:
    dependencies()
    record = {"spec": SPEC, "sha256": frozen.fingerprint(SPEC),
              "code_sha256": frozen.file_hash(Path(__file__), text=True),
              "protocol_sha256": frozen.file_hash(OUTPUT / "PROTOCOLO.md", text=True)}
    path = OUTPUT / "preregistro.json"
    if path.exists():
        if json.loads(path.read_text(encoding="utf-8")) != record:
            raise ValueError("Preregistro RCF modificado.")
    else:
        parent.save_json(path, record)
    return record


def score_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Only audited historical inputs; never access returns or ranking scores."""
    if (frame.index.has_duplicates or frame.entity_id.isna().any() or frame.entity_id.eq("").any()
            or not frame.division.isin(frozen.DIVISION_NAMES).all()):
        raise ValueError("Identidad/division incompleta o duplicada.")
    frame = frame.sort_index()
    result = frame[["entity_id", "division", "accn", "period", "filed_date", "accepted"]].copy()
    unique = ~frame.entity_id.duplicated(keep="first")
    buybacks = parent.numeric(frame, "buybacks_value")
    ocf = parent.numeric(frame, "ocf_value")
    capex = parent.numeric(frame, "capex_value")
    fcf = ocf - capex
    reported = frame[[name + "_status" for name in ("buybacks", "ocf", "capex")]].eq("reported").all(axis=1)
    matched = (frame.buybacks_start.eq(frame.ocf_start) & frame.capex_start.eq(frame.ocf_start)
               & frame.buybacks_end.eq(frame.ocf_end) & frame.capex_end.eq(frame.ocf_end)
               & frame.ocf_end.eq(frame.period) & frame.ocf_start.notna() & frame.ocf_start.ne(""))
    finite = np.isfinite(buybacks) & np.isfinite(ocf) & np.isfinite(capex) & np.isfinite(fcf)
    conditions = [
        (unique, "duplicate_share_class"),
        (frame.division.ne("H"), "financial_division_H"),
        (frame.filing_status.eq("current_annual_filing"), "no_current_annual_filing"),
        (frame.fact_source_status.eq("admitted_source_or_absent"), "source_quarantined"),
        (reported & finite & (buybacks >= 0) & (capex >= 0), "missing_or_invalid_component"),
        (matched & frame.fcf_status.eq("paired"), "cashflow_period_mismatch"),
        ((ocf > 0) & (fcf > 0), "nonpositive_cash_generation"),
        (buybacks > 0, "zero_reported_repurchase"),
        (buybacks <= fcf, "repurchases_exceed_fcf"),
    ]
    result["eligibility_reason"] = "eligible"
    eligible = pd.Series(True, index=frame.index)
    for condition, reason in conditions:
        result.loc[eligible & ~condition, "eligibility_reason"] = reason
        eligible &= condition
    result["eligible"] = eligible
    result["matched_fcf_usd"] = fcf.where(reported & matched & finite)
    result["repurchase_fraction"] = (buybacks / fcf.where(fcf > 0)).where(eligible)
    result["cash_conversion"] = (fcf / ocf.where(ocf > 0)).where(eligible)
    for name in ("repurchase_fraction", "cash_conversion"):
        result[name + "_pct"], result[name + "_global_fallback"] = parent.percentile(result[name], result.division)
    result[MODEL] = result[["repurchase_fraction_pct", "cash_conversion_pct"]].mean(axis=1).where(eligible)
    result.index.name = "symbol"
    return result


def inputs() -> tuple[dict[str, pd.DataFrame], dict]:
    result = audit.verify()  # verifies provenance, five artifacts and all frozen source hashes
    if frozen.fingerprint(result) != AUDIT_SHA256:
        raise ValueError("Resultado de inputs anual modificado.")
    annual = pd.read_csv(audit.OUTPUT / "annual_inputs.csv", float_precision="round_trip",
                         dtype={"entity_id": str, "symbol": str, "fecha": str}, keep_default_na=False)
    if annual.duplicated(["fecha", "symbol"]).any():
        raise ValueError("Inputs anuales duplicados.")
    frames, sources = parent.inputs()
    if set(annual.fecha) != set(frames):
        raise ValueError("Calendario anual distinto.")
    for day, original in frames.items():
        current = annual.loc[annual.fecha == day].set_index("symbol")
        if set(current.index) != set(original.index):
            raise ValueError("Universo anual distinto.")
        for column in ("entity_id", "division"):
            if not current[column].reindex(original.index).equals(original[column]):
                raise ValueError("Identidad anual distinta.")
        current["retorno"] = original.retorno
        frames[day] = current
    return frames, {**sources, "annual_audit_result": AUDIT_SHA256,
                    "annual_artifacts": result["artifacts_sha256"], "snapshot_sha256": result["fact_sources"]["snapshot_sha256"]}


def bootstrap_bounds(excess: pd.DataFrame) -> dict:
    bounds: dict = dict.fromkeys(excess.columns, None)
    n = len(excess)
    if n < 30:
        return bounds
    settings = SPEC["bootstrap"]
    rng = np.random.default_rng(settings["seed"])
    starts = rng.integers(0, n, size=(settings["replicas"], int(np.ceil(n / settings["blocks"]))))
    indices = ((starts[:, :, None] + np.arange(settings["blocks"])) % n).reshape(settings["replicas"], -1)[:, :n]
    for column in excess:
        array = excess[column].to_numpy(dtype=float)
        if np.isfinite(array).all():
            bounds[column] = float(np.quantile(array[indices].mean(axis=1), settings["lower_tail"]))
    return bounds


def summarize(panel: pd.DataFrame) -> dict:
    if panel.fecha.duplicated().any() or not panel.fecha.is_monotonic_increasing:
        raise ValueError("Calendario del diagnostico invalido.")
    test = parent.ic_test(panel.ic)
    test["p_known_search_guard"] = min(1., SEARCH_COUNT_LOWER_BOUND * test["p"])
    bounds = bootstrap_bounds(panel[["excess_base", "excess_stress"]])
    failures = []
    if test["mean"] is None or test["mean"] <= 0 or test["p"] >= ALPHA:
        failures.append("ic_not_positive_after_known_search_guard")
    sample = panel.loc[panel.n_scored >= 30]
    sample_windows = {name: int(((sample.fecha >= start) & (sample.fecha < end)).sum())
                      for name, (start, end) in frozen.WINDOWS.items()}
    if len(sample) < 30 or any(count < 8 for count in sample_windows.values()):
        failures.append("insufficient_eligible_issuer_sample")
    costs = {}
    for cost in parent.COSTS:
        name = f"excess_{cost}"
        valid = panel.loc[np.isfinite(panel[name])]
        windows = {}
        for window, (start, end) in frozen.WINDOWS.items():
            sub = valid.loc[(valid.fecha >= start) & (valid.fecha < end)]
            mean = float(sub[name].mean()) if len(sub) else None
            windows[window] = {"n": len(sub), "mean_excess": mean}
            if len(sub) < 8 or mean is None or mean <= 0:
                failures.append(f"{cost}_{window}_insufficient_or_nonpositive")
        lower = bounds[name]
        if len(valid) < 30 or lower is None or lower <= 0:
            failures.append(f"{cost}_insufficient_or_lower_bound_nonpositive")
        control = panel[f"selection_excess_{cost}"]
        costs[cost] = {"n": len(valid), "mean_excess": float(valid[name].mean()) if len(valid) else None,
                       "known_search_lower_bound": lower, "windows": windows,
                       "invalid_dates": panel.loc[~np.isfinite(panel[name]), "fecha"].tolist(),
                       "mean_selection_excess_vs_eligible": float(control.mean()) if control.notna().any() else None,
                       "n_selection_control": int(control.notna().sum())}
    return {"ic": test, "costs": costs, "audit_daily": not failures, "failures": failures,
            "demonstrated": False, "n_dates_with_30_eligible": len(sample), "sample_windows": sample_windows,
            "minimum_scored": int(panel.n_scored.min()), "maximum_scored": int(panel.n_scored.max()),
            "minimum_selected": int(panel.n_selected.min()), "maximum_selected": int(panel.n_selected.max())}


def analyze(destination: Path = OUTPUT) -> dict:
    record = preregister()
    if (destination / "resultado.json").exists():
        raise ValueError("Resultado RCF ya congelado; no se sobrescribe.")
    frames, sources = inputs()
    spy, snapshot = parent.benchmark(sorted(frames))
    if snapshot != sources["snapshot_sha256"]:
        raise ValueError("Snapshot anual/precios distinto.")
    all_scores, all_decisions, quarters, coverage = [], [], [], []
    for day in sorted(frames):
        frame = frames[day]
        scores = score_frame(frame)
        all_scores.append(scores.reset_index().assign(fecha=day))
        chosen = parent.decisions(scores, MODEL)
        if chosen.loc[chosen.reason == "selected", "entity_id"].duplicated().any():
            raise ValueError("Cartera con CIK duplicado.")
        chosen["eligibility_reason"] = chosen.symbol.map(scores.eligibility_reason)
        all_decisions.append(chosen.assign(fecha=day))
        selected = chosen.loc[chosen.reason == "selected", "symbol"]
        returns = frame.retorno.reindex(selected).to_numpy(dtype=float)
        eligible = scores.index[scores.eligible]
        control_returns = frame.retorno.reindex(eligible).to_numpy(dtype=float)
        pairs = pd.concat([scores[MODEL], frame.retorno], axis=1).replace([np.inf, -np.inf], np.nan).dropna()
        pairs = pairs.loc[pairs.retorno >= -1]
        ic = float(stats.spearmanr(pairs[MODEL], pairs.retorno).statistic) if (
            len(pairs) >= 30 and pairs[MODEL].nunique() > 1 and pairs.retorno.nunique() > 1) else None
        row = {"fecha": day, "model": MODEL, "n_universe": len(frame), "n_issuers": frame.entity_id.nunique(),
               "n_scored": len(eligible), "n_pairs": len(pairs), "ic": ic, "n_selected": len(selected),
               "cash_budget_weight": (20 - len(selected)) / 20,
               "missing_selected": ";".join(selected.loc[~np.isfinite(returns) | (returns < -1)].tolist())}
        for cost, bps in parent.COSTS.items():
            value = parent.funded_return(returns, bps)
            control = parent.funded_return(control_returns, bps, slots=len(eligible)) if len(eligible) else None
            row.update({f"net_{cost}": value, f"eligible_net_{cost}": control,
                        f"excess_{cost}": value - float(spy.loc[day, f"spy_{cost}"]) if value is not None else None,
                        f"selection_excess_{cost}": value - control if value is not None and control is not None else None})
        quarters.append(row)
        for kind, name, sub in [("all", "all", scores), *[("division", division, part) for division, part in scores.groupby("division")]]:
            coverage.append({"fecha": day, "stratum": kind, "group": name, "n_security_rows": len(sub),
                             "n_issuers": sub.entity_id.nunique(), "n_eligible": int(sub.eligible.sum()),
                             "reasons": json.dumps(sub.eligibility_reason.value_counts().to_dict(), sort_keys=True)})
    panel = pd.DataFrame(quarters)
    tables = {"scores.csv": pd.concat(all_scores, ignore_index=True),
              "decisions.csv": pd.concat(all_decisions, ignore_index=True), "quarterly.csv": panel,
              "benchmark_periods.csv": spy.reset_index(), "coverage.csv": pd.DataFrame(coverage)}
    destination.mkdir(parents=True, exist_ok=True)
    for name, table in tables.items():
        table.to_csv(destination / name, index=False, lineterminator="\n")
    result = {"spec_sha256": record["sha256"], "code_sha256": record["code_sha256"],
              "protocol_sha256": record["protocol_sha256"], "inputs": sources,
              "stage": SPEC["stage"], "demonstrated": False, "model": MODEL,
              "new_configurations": 1, "search_count_lower_bound": SEARCH_COUNT_LOWER_BOUND,
              "summary": summarize(panel),
              "artifacts_sha256": {name: frozen.file_hash(destination / name, text=True) for name in tables},
              "versions": {"pandas": pd.__version__, "numpy": np.__version__, "scipy": parent.scipy.__version__,
                           "exchange_calendars": parent.xcals.__version__},
              "limitations": ["observed retrospective history, not independent validation",
                              "nonrandom missing standard tags and source quarantine may bias eligible subset",
                              "FCF is OCF minus PP&E purchases; omits other investment, debt, dividends and share issuance",
                              "gross repurchases do not establish net share retirement or absence of borrowed funds",
                              "alphabetical single share class need not be most liquid; no price/valuation normalization",
                              "known-trial guard is not global error control; full search ledger unreconciled",
                              "independent holding periods with inherited terminal/non-strict equity exits; no CAGR/daily risk"],
              "next_step": "daily funded audit only if all gates pass; otherwise archive unchanged failed candidate"}
    parent.save_json(destination / "resultado.json", result)
    return result


def verify() -> dict:
    record = preregister()
    result = json.loads((OUTPUT / "resultado.json").read_text(encoding="utf-8"))
    for field in ("spec_sha256", "code_sha256", "protocol_sha256"):
        expected = record["sha256"] if field == "spec_sha256" else record[field]
        if result[field] != expected:
            raise ValueError("Sello RCF modificado.")
    if set(result["artifacts_sha256"]) != ARTIFACTS:
        raise ValueError("Artefactos RCF incompletos.")
    for name, expected in result["artifacts_sha256"].items():
        if frozen.file_hash(OUTPUT / name, text=True) != expected:
            raise ValueError(f"Artefacto modificado: {name}")
    frames, sources = inputs()
    spy, snapshot = parent.benchmark(sorted(frames))
    if sources != result["inputs"] or snapshot != sources["snapshot_sha256"]:
        raise ValueError("Fuentes RCF modificadas.")
    saved_spy = pd.read_csv(OUTPUT / "benchmark_periods.csv", float_precision="round_trip").set_index("fecha")
    pd.testing.assert_frame_equal(saved_spy, spy, check_exact=False, rtol=1e-12, atol=1e-12)
    calculated = summarize(pd.read_csv(OUTPUT / "quarterly.csv", float_precision="round_trip"))
    if frozen.fingerprint(calculated) != frozen.fingerprint(result["summary"]):
        raise ValueError("Resumen RCF no reproducido.")
    if result["demonstrated"] or result["summary"]["demonstrated"]:
        raise ValueError("Un diagnostico retrospectivo no demuestra una estrategia.")
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
