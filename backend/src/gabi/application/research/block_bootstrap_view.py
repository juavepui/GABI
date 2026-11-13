"""Block-bootstrap tables and histograms, as the Research Lab page presented them."""

import math

import numpy as np
import pandas as pd

LABELS = {"cagr": "CAGR anual", "volatility": "Volatilidad anual", "sharpe": "Sharpe anual",
          "max_drawdown": "Drawdown máximo", "es5": "ES5 por observación",
          "excess_mean": "Exceso medio por observación", "cagr_difference": "Diferencia de CAGR anual",
          "sharpe_difference": "Diferencia de Sharpe", "mean": "Media temporal"}
SERIES = {"strategy": "GABI", "spy": "SPY", "SPY": "SPY", "eligible_universe": "Universo elegible",
          "ic": "Rank IC", "q5_menos_q1": "Spread Q5−Q1"}
HISTOGRAM_BINS = 45


def series_name(name: str) -> str:
    if name.startswith("vs_"):
        return "GABI frente a " + SERIES.get(name[3:], name[3:])
    return SERIES.get(name, name)


def _number(value):
    if value is None or isinstance(value, bool | str):
        return value
    value = float(value)
    return value if math.isfinite(value) else None


def _runs(audit: dict, order: list[str] | None) -> list[tuple[str, dict]]:
    """Runs in their preregistered order (primary first); sorted-key artifacts pass it explicitly."""
    return [(block, audit["runs"][block]) for block in (order or list(audit["runs"]))]


def interval_rows(audit: dict, order: list[str] | None = None) -> list[dict]:
    """block_bootstrap.interval_table, with display names next to the original keys."""
    rows: list[dict] = []
    for block, run in _runs(audit, order):
        entries = [(name, metric, summary) for name, series in run.get("series", {}).items()
                   for metric, summary in series["metrics"].items()]
        entries += [(f"vs_{name}", metric, summary) for name, comparison in run.get("comparisons", {}).items()
                    for metric, summary in comparison["metrics"].items()]
        entries += [(name, "mean", mean["summary"]) for name, mean in run.get("means", {}).items()]
        for name, metric, summary in entries:
            rows.append({"block_size": int(block), "series": name, "series_label": series_name(name),
                         "metric": metric, "metric_label": LABELS[metric]}
                        | {key: _number(value) for key, value in summary.items()})
    return rows


def comparison_rows(audit: dict, order: list[str] | None = None) -> list[dict]:
    rows = []
    for block, run in _runs(audit, order):
        entries = {f"vs_{name}": (value["metrics"]["excess_mean"], value["hac"])
                   for name, value in run.get("comparisons", {}).items()}
        entries.update({name: (value["summary"], value["hac"]) for name, value in run.get("means", {}).items()})
        for name, (summary, hac) in entries.items():
            rows.append({"block_size": int(block), "series": series_name(name), "mean": _number(summary["observed"]),
                         "bootstrap_lower": _number(summary["lower"]), "bootstrap_upper": _number(summary["upper"]),
                         "hac_lower": _number(hac["lower"]), "hac_upper": _number(hac["upper"]),
                         "hac_lags": hac["hac_lags"], "zero_conclusion_differs": bool(hac["zero_conclusion_differs"])})
    return rows


def fraction_rows(run: dict) -> list[dict]:
    rows = []
    for name, series in run.get("series", {}).items():
        rows.append({"series": series_name(name),
                     "condition": f"Drawdown ≥ {run['drawdown_threshold']:.0%} de pérdida",
                     **series["drawdown_fraction"]})
    for name, comparison in run.get("comparisons", {}).items():
        rows.extend({"series": series_name(f"vs_{name}"), "condition": LABELS[metric] + " > 0", **fraction}
                    for metric, fraction in comparison["positive_fractions"].items())
    for name, mean in run.get("means", {}).items():
        rows.append({"series": series_name(name), "condition": "Media > 0", **mean["positive_fraction"]})
    return [{"series": row["series"], "condition": row["condition"], "fraction": _number(row["fraction"]),
             "valid_draws": int(row["valid_draws"]), "undefined_draws": int(row["undefined_draws"])} for row in rows]


def _observed(run: dict, column: str) -> float | None:
    if "/" in column:
        series, metric = column.split("/", 1)
        records = run["comparisons"][series[3:]] if series.startswith("vs_") else run["series"][series]
        return _number(records["metrics"][metric]["observed"])
    if column in run.get("means", {}):
        return _number(run["means"][column]["summary"]["observed"])
    return None


def histograms(audit: dict, distribution: pd.DataFrame) -> list[dict]:
    """Primary-block replicate distribution per column: fraction per bin and the percentile interval."""
    primary = audit["runs"][str(audit["primary_block"])]
    rows = distribution.loc[distribution["block_size"] == audit["primary_block"]]
    result = []
    for column in (name for name in distribution if name not in ("replicate", "block_size")):
        values = rows[column].to_numpy(dtype=float)
        values = values[np.isfinite(values)]
        if "/" in column:
            series, metric = column.split("/", 1)
            label = f"{series_name(series)} · {LABELS.get(metric, column)}"
        else:
            label = series_name(column)
        item = {"column": column, "label": label, "observed": _observed(primary, column),
                "valid_draws": len(values), "bins": [], "lower": None, "upper": None}
        if len(values):
            try:
                counts, edges = np.histogram(values, bins=HISTOGRAM_BINS)
            except ValueError:  # range below float resolution for 45 bins: one bin, not an error
                counts, edges = np.histogram(values, bins=1)
            low, high = np.quantile(values, [(1 - primary["ci"]) / 2, (1 + primary["ci"]) / 2])
            item |= {"lower": float(low), "upper": float(high),
                     "bins": [{"start": float(edges[i]), "end": float(edges[i + 1]),
                               "fraction": float(counts[i] / len(values))} for i in range(len(counts))]}
        result.append(item)
    return result


def present(audit: dict, distribution: pd.DataFrame, order: list[str] | None = None) -> dict:
    primary = audit["runs"][str(audit["primary_block"])]
    return {
        "primary_block": int(audit["primary_block"]), "n_obs": int(primary["n_obs"]),
        "periods_per_year": int(primary["periods_per_year"]), "n_boot": int(primary["n_boot"]),
        "ci": float(primary["ci"]), "start": str(primary["start"]), "end": str(primary["end"]),
        "has_series": bool(primary.get("series")),
        "tail_sparse": any(value.get("tail_sparse") for value in primary.get("series", {}).values()),
        "tail_mass": float(primary["n_obs"]) * .05,
        "limitations": list(primary["limitations"]),
        "intervals": interval_rows(audit, order), "fractions": fraction_rows(primary),
        "comparisons": comparison_rows(audit, order), "histograms": histograms(audit, distribution),
    }
