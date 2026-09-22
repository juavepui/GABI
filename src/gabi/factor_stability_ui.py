"""Vista compartida del backtest actual y de la auditoría temporal guardada."""
import json

import pandas as pd

from . import factor_stability as fs


def render(audit: dict, *, key: str) -> None:
    import plotly.graph_objects as go
    import streamlit as st

    st.caption(
        f"{audit['n_obs']} trimestres · FF5 + Momentum · mínimo {fs.MIN_OBS} observaciones por ajuste local. "
        "Diagnóstico retrospectivo; intervalos HAC puntuales y aproximados."
    )
    st.dataframe(pd.DataFrame([
        {"Muestra": label, "Desde": fit.get("start"), "Hasta": fit.get("end"),
         "n": fit["n_obs"], "g.l.": fit["dof"], "Estado": fit["status"],
         "Alfa anualizado": fit.get("alpha_anualizado"), "t alfa HAC": fit.get("t_stat", {}).get("alpha"),
         **{f"Beta {name}": fit.get("coef", {}).get(name) for name in fs.NAMES[1:]}}
        for label, fit in [("Completa", audit["full"]),
                           ("Primera mitad", audit["halves"][0]), ("Segunda mitad", audit["halves"][1])]
    ]), hide_index=True, width="stretch")
    c1, c2 = st.columns(2)
    name = c1.selectbox("Coeficiente", fs.NAMES, key=f"{key}_coefficient")
    window = c2.selectbox("Ventana (trimestres)", fs.WINDOWS, key=f"{key}_window")
    table = fs.coefficient_table(audit)
    selected = table.loc[(table["group"] == f"rolling_{window}") & (table["coefficient"] == name)]
    if selected.empty:
        st.info("La muestra no alcanza la longitud de esta ventana.")
    else:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=selected["end"], y=selected["ci_high"], mode="lines",
                                 line={"width": 0}, showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=selected["end"], y=selected["ci_low"], mode="lines",
                                 line={"width": 0}, fill="tonexty", name="IC 95% puntual HAC"))
        fig.add_trace(go.Scatter(x=selected["end"], y=selected["estimate"], mode="lines+markers",
                                 name=name, customdata=selected[["start", "n_obs", "t_hac"]],
                                 hovertemplate="%{customdata[0]} → %{x}<br>Coef.: %{y:.4f}"
                                               "<br>n=%{customdata[1]} · t HAC=%{customdata[2]:.2f}<extra></extra>"))
        fig.add_hline(y=audit["full"]["coef"][name], line_dash="dash", annotation_text="Muestra completa")
        fig.add_hline(y=0, line_color="gray")
        fig.update_layout(xaxis_title="Fin de la ventana", yaxis_title="Alfa trimestral" if name == "alpha" else "Beta")
        st.plotly_chart(fig, width="stretch", key=f"{key}_chart")
    st.caption("Las ventanas se solapan. Los cambios visuales y los intervalos puntuales no prueban un cambio de régimen.")
    st.markdown("**Concentración por episodios**")
    st.dataframe(pd.DataFrame([
        {"Episodio": event["label"], "n": event["n_obs"],
         "Retorno compuesto": event["compounded_return"],
         "Contribución al alfa trimestral global (pp)": 100 * event["attribution"]["contribution_to_full_quarterly_alpha"],
         "Regresión local": event["local_regression"]["status"],
         "Alfa anualizado al excluir episodio": (event["without_episode"] or {}).get("alpha_anualizado")}
        for event in audit["events"]
    ]), hide_index=True, width="stretch")
    st.caption(
        "Contribución = suma de (exceso de retorno − exposición a factores con betas globales) / n total. "
        "Las filas suman el alfa trimestral global; no son alfas estimados por episodio ni retornos compuestos. "
        "Los ajustes al excluir episodios solo muestran coeficientes, sin t-stats sobre fechas con huecos. "
        "insufficient_data significa que no se estima alfa/betas locales con tan pocas observaciones."
    )
    with st.expander("Alcance y datos completos"):
        st.caption("Atribución por año de inicio del trimestre (los años extremos pueden estar incompletos). "
                   "adjusted_sum es suma aritmética ajustada por betas globales, no alfa anual.")
        st.dataframe(pd.DataFrame(audit["calendar_years"]), hide_index=True, width="stretch")
        for limitation in audit["limitations"]:
            st.write(limitation)
        st.download_button("Descargar coeficientes e intervalos", table.to_csv(index=False).encode("utf-8"),
                           file_name="factor-stability-coefficients.csv", mime="text/csv", key=f"{key}_csv")
        st.download_button("Descargar diagnóstico completo", json.dumps(fs._json_safe(audit), ensure_ascii=False,
                           indent=2, allow_nan=False).encode("utf-8"), file_name="factor-stability.json",
                           mime="application/json", key=f"{key}_json")
