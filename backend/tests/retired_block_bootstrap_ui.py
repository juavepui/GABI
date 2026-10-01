"""Reference copy of the table helpers of the retired Streamlit `block_bootstrap_ui` (#68).

Kept verbatim so the React presentation keeps being compared with what the old page showed.
"""

import pandas as pd

LABELS = {"cagr": "CAGR anual", "volatility": "Volatilidad anual", "sharpe": "Sharpe anual",
          "max_drawdown": "Drawdown máximo", "es5": "ES5 por observación",
          "excess_mean": "Exceso medio por observación", "cagr_difference": "Diferencia de CAGR anual",
          "sharpe_difference": "Diferencia de Sharpe", "mean": "Media temporal"}
SERIES = {"strategy": "GABI", "spy": "SPY", "SPY": "SPY", "eligible_universe": "Universo elegible",
          "ic": "Rank IC", "q5_menos_q1": "Spread Q5−Q1"}


def _name(name: str) -> str:
    if name.startswith("vs_"):
        return "GABI frente a " + SERIES.get(name[3:], name[3:])
    return SERIES.get(name, name)


def comparison_table(audit: dict) -> pd.DataFrame:
    rows = []
    for block, run in audit["runs"].items():
        entries = {f"vs_{name}": (value["metrics"]["excess_mean"], value["hac"])
                   for name, value in run.get("comparisons", {}).items()}
        entries.update({name: (value["summary"], value["hac"]) for name, value in run.get("means", {}).items()})
        for name, (summary, hac) in entries.items():
            rows.append({"Bloque": int(block), "Serie": _name(name), "Media": summary["observed"],
                         "Bootstrap inferior": summary["lower"], "Bootstrap superior": summary["upper"],
                         "HAC inferior": hac["lower"], "HAC superior": hac["upper"],
                         "Retardos HAC": hac["hac_lags"], "Difieren al excluir cero": hac["zero_conclusion_differs"]})
    return pd.DataFrame(rows)


def fraction_table(run: dict) -> pd.DataFrame:
    rows = []
    for name, series in run.get("series", {}).items():
        rows.append({"Serie": _name(name), "Condición": f"Drawdown ≥ {run['drawdown_threshold']:.0%} de pérdida",
                     **series["drawdown_fraction"]})
    for name, comparison in run.get("comparisons", {}).items():
        rows.extend({"Serie": _name(f"vs_{name}"), "Condición": LABELS[metric] + " > 0", **fraction}
                    for metric, fraction in comparison["positive_fractions"].items())
    for name, mean in run.get("means", {}).items():
        rows.append({"Serie": _name(name), "Condición": "Media > 0", **mean["positive_fraction"]})
    return pd.DataFrame(rows).rename(columns={"fraction": "Fracción bootstrap", "valid_draws": "Réplicas válidas",
                                              "undefined_draws": "No estimables"})
