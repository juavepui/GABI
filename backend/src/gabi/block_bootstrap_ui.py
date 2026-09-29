"""Research Lab presentation of saved and on-demand block-bootstrap diagnostics."""

import json

import numpy as np
import pandas as pd

from . import block_bootstrap as bb

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


def render(audit: dict, distribution: pd.DataFrame, *, key: str) -> None:
    import plotly.graph_objects as go
    import streamlit as st

    primary = audit["runs"][str(audit["primary_block"])]
    st.warning("Remuestrear el pasado no genera evidencia OOS nueva. Las fracciones bootstrap no son "
               "p-valores ni probabilidades de éxito futuro.")
    st.caption(f"{primary['n_obs']} observaciones · {primary['periods_per_year']} por año · "
               f"{primary['n_boot']:,} réplicas · bloque principal {primary['block_size']} · "
               f"intervalo percentil {primary['ci']:.0%}. Dependencia dentro de bloques, con uniones artificiales.")
    table = bb.interval_table(audit)
    shown = table.loc[table.block_size == audit["primary_block"]].copy()
    shown["series"] = shown["series"].map(_name)
    shown["metric"] = shown["metric"].map(LABELS)
    st.caption("Retornos, volatilidad, drawdown y ES en fracción (0,10 = 10 %); Sharpe e IC sin unidades. "
               "ES tiene el horizonte de una observación original. Drawdown negativo incluye capital inicial. "
               "Los rangos de drawdown/ES son descriptivos y no tienen cobertura garantizada.")
    if primary.get("series"):
        st.caption("El drawdown es el máximo durante toda la trayectoria remuestreada, "
                   "de la misma duración que el histórico; su fracción no describe el riesgo de un solo año.")
    st.dataframe(shown.rename(columns={"series": "Serie", "metric": "Métrica", "observed": "Observado",
                                      "lower": "Inferior", "median": "Mediana bootstrap", "upper": "Superior",
                                      "bootstrap_mean": "Media bootstrap", "valid_draws": "Réplicas válidas",
                                      "undefined_draws": "No estimables"}).drop(columns="block_size"),
                 hide_index=True, width="stretch")
    st.dataframe(fraction_table(primary), hide_index=True, width="stretch")
    if any(value.get("tail_sparse") for value in primary.get("series", {}).values()):
        st.caption(f"Cola ES5 escasa: masa de {primary['n_obs'] * .05:.2f} observaciones. "
                   "Las réplicas no crean nuevos episodios extremos.")
    candidates = [col for col in distribution if col not in ("replicate", "block_size")]
    selected = st.selectbox("Distribución del remuestreo", candidates, key=f"{key}_metric",
                            format_func=lambda col: (f"{_name(col.split('/')[0])} · {LABELS.get(col.split('/')[-1], col)}"
                                                     if "/" in col else _name(col)))
    values = distribution.loc[distribution.block_size == audit["primary_block"], selected]
    values = values.loc[np.isfinite(values)]
    if values.empty:
        st.info("Esta métrica no es estimable en ninguna réplica; no se dibuja una distribución artificial.")
    else:
        fig = go.Figure(go.Histogram(x=values, nbinsx=45, histnorm="probability", name="Fracción de réplicas"))
        low, high = np.quantile(values, [(1 - primary["ci"]) / 2, (1 + primary["ci"]) / 2])
        fig.add_vline(x=float(low), line_dash="dot")
        fig.add_vline(x=float(high), line_dash="dot")
        observed = None
        if "/" in selected:
            series, metric = selected.split("/", 1)
            records = primary["comparisons"][series[3:]] if series.startswith("vs_") else primary["series"][series]
            observed = records["metrics"][metric]["observed"]
        elif selected in primary.get("means", {}):
            observed = primary["means"][selected]["summary"]["observed"]
        if observed is not None:
            fig.add_vline(x=observed, line_color="red", annotation_text="Observado")
        fig.update_layout(xaxis_title=selected, yaxis_title="Fracción de réplicas", showlegend=False)
        st.plotly_chart(fig, width="stretch", key=f"{key}_histogram")
    with st.expander("Sensibilidad de bloques y comparación con HAC/Newey-West"):
        st.caption("Las longitudes se fijaron antes del análisis. Se presentan todas; no se selecciona la más favorable.")
        st.dataframe(table, hide_index=True, width="stretch")
        comparison = comparison_table(audit)
        if not comparison.empty:
            st.dataframe(comparison, hide_index=True, width="stretch")
            st.caption("HAC compara medias, no CAGR, Sharpe ni drawdown. Diferencias al excluir cero "
                       "reflejan métodos y aproximaciones distintos; no deciden cuál es correcto.")
    with st.expander("Parámetros y descarga reproducible"):
        for limitation in primary["limitations"]:
            st.write(limitation)
        st.download_button("Descargar parámetros e intervalos", json.dumps(audit, ensure_ascii=False, indent=2,
                           allow_nan=False).encode("utf-8"), file_name="block-bootstrap.json", mime="application/json", key=f"{key}_json")
        st.download_button("Descargar todas las réplicas", distribution.to_csv(index=False).encode("utf-8"),
                           file_name="block-bootstrap-distributions.csv", mime="text/csv", key=f"{key}_csv")
