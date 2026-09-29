"""Riesgo de cola con horizonte y resolución muestral visibles."""
import json

import pandas as pd

from . import portfolio_metrics as pm


def render_returns(series: dict[str, pd.Series], *, horizon: str, key: str) -> dict:
    import streamlit as st

    summaries = {}
    for name, returns in series.items():
        try:
            summaries[name] = pm.tail_risk_metrics(returns, horizon=horizon)
        except (ValueError, TypeError) as exc:
            st.warning(f"Riesgo de cola de {name} no disponible: {exc}")
    if not summaries:
        return summaries
    st.caption(f"Horizonte: {horizon}. Estimaciones históricas sin anualizar; pérdidas positivas, ganancias negativas.")
    rows = []
    for name, summary in summaries.items():
        rows.append({
            "Cartera": name, "n": summary["n_obs"],
            "VaR 95%": summary["95"]["var"], "ES/CVaR 95%": summary["95"]["expected_shortfall"],
            "VaR 99%": summary["99"]["var"], "ES/CVaR 99%": summary["99"]["expected_shortfall"],
            "Asimetría": summary["skewness"], "Exceso de curtosis": summary["excess_kurtosis"],
            "Masa de cola 95%": summary["95"]["tail_mass"], "Masa de cola 99%": summary["99"]["tail_mass"],
        })
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", column_config={
        **{name: st.column_config.NumberColumn(format="percent")
           for name in ("VaR 95%", "ES/CVaR 95%", "VaR 99%", "ES/CVaR 99%")},
        **{name: st.column_config.NumberColumn(format="%.3f") for name in ("Asimetría", "Exceso de curtosis")},
        **{name: st.column_config.NumberColumn(format="%.2f") for name in ("Masa de cola 95%", "Masa de cola 99%")},
    })
    for name, summary in summaries.items():
        for level in ("95", "99"):
            tail = summary[level]
            if tail["status"] == "empty":
                st.info(f"{name}: no hay retornos para estimar la cola al {level}%.")
            elif tail["status"] == "below_resolution":
                st.warning(f"{name} · {level}%: masa de cola {tail['tail_mass']:.2f} < 1 observación. "
                           "VaR y ES coinciden con la peor pérdida observada; el extremo no está resuelto por la muestra.")
            elif tail["status"] == "sparse":
                st.warning(f"{name} · {level}%: cola escasa ({tail['tail_mass']:.2f} observaciones equivalentes). "
                           "El resultado depende de muy pocos retornos.")
    st.caption(
        "VaR es el umbral de pérdidas; ES/CVaR promedia la peor masa del 5% o 1%, ponderando la frontera. "
        "Asimetría negativa indica cola izquierda; exceso de curtosis normal = 0 (no 3). "
        "La masa de cola no cuenta eventos independientes. Estas cifras describen la muestra y no limitan las pérdidas futuras."
    )
    st.download_button("Descargar riesgo de cola", json.dumps(summaries, ensure_ascii=False, indent=2,
                       allow_nan=False).encode("utf-8"), file_name="tail-risk.json", mime="application/json", key=key)
    return summaries


def render_nav(curves: dict[str, pd.Series], *, key: str) -> dict:
    import streamlit as st

    returns = {}
    for name, nav in curves.items():
        try:
            returns[name] = pm.returns_from_nav(nav)
        except (ValueError, TypeError) as exc:
            st.warning(f"NAV de {name} no utilizable para riesgo de cola: {exc}")
    return render_returns(returns, horizon="una sesión (NAV diario)", key=key)
