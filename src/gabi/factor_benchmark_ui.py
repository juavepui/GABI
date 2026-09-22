"""Comparación de riqueza contra benchmarks sintéticos con exposición estimada."""
import json

import pandas as pd

from . import factor_benchmark as fb
from . import factor_stability as fs

LABELS = {"strategy": "Estrategia", "spy": "SPY", "rf": "RF", "universe_ew": "Universo EW",
          "spy_beta": "SPY ajustado por beta", "ff6": "FF5 + Momentum sin alfa"}


def render(audit: dict, *, key: str) -> None:
    import streamlit as st

    mode = st.radio("Estimación de exposiciones", ["expanding", "in_sample"],
                    format_func=lambda value: "Expansiva con datos anteriores" if value == "expanding"
                    else "Muestra completa (atribución retrospectiva)", horizontal=True, key=f"{key}_mode")
    result = audit[mode]
    if mode == "in_sample":
        st.warning("Estas betas utilizan toda la muestra, incluidos los periodos representados. "
                   "La curva es un diagnóstico retrospectivo, no un backtest sin anticipación.")
    else:
        st.caption(f"Mínimo {audit['method']['min_train']} trimestres de entrenamiento, "
                   f"{audit['method']['embargo_quarters']} trimestre de embargo, sin incluir alfa en el benchmark. "
                   "Los factores históricos revisados no certifican disponibilidad point-in-time ni validación prospectiva.")
    if not result["n_obs"]:
        st.info("No hay suficiente historia tras entrenamiento y embargo para construir esta comparación.")
        return
    st.caption(f"{result['n_obs']} trimestres: {result['start']} → {result['end']}. "
               "Todas las curvas parten de 1 en la misma fecha; no se rellena el entrenamiento con ceros.")
    st.line_chart(fb.curve_table(result).rename(columns=LABELS))
    st.dataframe(pd.DataFrame([
        {"Referencia": LABELS[name], "Retorno acumulado": metrics["total_return"], "CAGR": metrics["cagr"]}
        for name, metrics in result["metrics"].items()
    ]), hide_index=True, width="stretch", column_config={
        name: st.column_config.NumberColumn(format="percent") for name in ("Retorno acumulado", "CAGR")
    })
    st.dataframe(pd.DataFrame([
        {"Referencia": LABELS[name], "Exceso medio trimestral": metrics["mean_active_per_quarter"],
         "Diferencia de CAGR (pp)": 100 * metrics["cagr_difference"],
         "Exceso de riqueza relativa": metrics["relative_wealth_return"]}
        for name, metrics in result["active"].items()
    ]), hide_index=True, width="stretch", column_config={
        "Exceso medio trimestral": st.column_config.NumberColumn(format="percent"),
        "Diferencia de CAGR (pp)": st.column_config.NumberColumn(format="%.2f"),
        "Exceso de riqueza relativa": st.column_config.NumberColumn(format="percent"),
    })
    st.caption("Exceso de riqueza = capital estrategia / capital benchmark − 1. "
               "La diferencia de CAGR no es el alfa de regresión; el exceso tampoco prueba habilidad de selección.")
    if mode == "in_sample":
        st.dataframe(pd.DataFrame([
            {"Modelo": LABELS[name], "Alfa trimestral OLS": fit["coef"]["alpha"],
             "t alfa HAC": fit["t_stat"]["alpha"], **{c: v for c, v in fit["coef"].items() if c != "alpha"}}
            for name, fit in result["regressions"].items()
        ]), hide_index=True, width="stretch")
    else:
        with st.expander("Exposiciones y fecha de cada entrenamiento"):
            st.dataframe(pd.DataFrame([
                {**{k: v for k, v in row.items() if k != "coef"}, **row["coef"]}
                for row in result["coefficients"]
            ]), hide_index=True, width="stretch")
            st.caption("El intercepto se estima para calcular correctamente las betas, pero no se añade al benchmark.")
    with st.expander("Supuestos y descarga"):
        for limitation in audit["limitations"]:
            st.write(limitation)
        st.download_button("Descargar curvas comparables", fb.curve_table(result).to_csv().encode("utf-8"),
                           file_name=f"factor-benchmark-{mode}.csv", mime="text/csv", key=f"{key}_csv")
        st.download_button("Descargar benchmark completo", json.dumps(fs._json_safe(audit), ensure_ascii=False,
                           indent=2, allow_nan=False).encode("utf-8"), file_name="factor-benchmark.json",
                           mime="application/json", key=f"{key}_json")
