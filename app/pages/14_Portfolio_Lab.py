import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import pandas as pd
import streamlit as st

from gabi import portfolio_lab as pl
from gabi import tail_risk_ui

st.title("🧮 Portfolio Lab")
st.caption(
    "Una vez sólido el motor de backtest, la pregunta siguiente no es \"¿qué empresas elegimos?\" sino "
    "\"¿cómo repartimos el capital entre ellas?\". Compara, sin declarar ganador de antemano, seis formas "
    "de ponderar las MISMAS candidatas de cada rebalanceo: **Equal Weight, Inverse Volatility, Minimum "
    "Variance, Score-weighted, Score + risk constrained y Risk Parity**."
)
st.warning(
    "⚠️ Para un junior es mucho más útil decir \"esta cartera tiene 20 empresas, pero 3 de ellas "
    "representan un 34% del RIESGO\" que enseñarle \"20 posiciones = diversificada\". Fíjate en HHI y "
    "Top-3 contribution-to-risk, no solo en el número de posiciones.",
    icon="⚠️",
)

with st.expander("ℹ️ Qué significa cada esquema (léelo si no los conoces)"):
    st.markdown(
        """
- **Equal Weight**: mismo % de capital en cada posición — el caso base, ni mejor ni peor de antemano.
- **Inverse Volatility**: más peso a las acciones MENOS volátiles individualmente (no mira correlaciones).
- **Minimum Variance**: la combinación de pesos que minimiza la volatilidad TOTAL de la cartera (sí mira
  correlaciones/covarianza) — sin límites de posición ni sector.
- **Score-weighted**: peso proporcional al composite score — las mejor puntuadas se llevan más capital.
- **Score + risk constrained**: igual que Score-weighted, pero maximizando utilidad media-varianza sujeta
  a límites de posición y sector DENTRO del propio optimizador (PyPortfolioOpt) — si esos límites hacen el
  problema inviable para el conjunto concreto de candidatas, cae automáticamente a Score-weighted para ese
  periodo (igual filosofía de respaldo que ya usan Decisiones de cartera).
- **Risk Parity**: cada posición aporta la MISMA fracción del riesgo total — no el mismo peso en $ (eso es
  Equal Weight) ni la misma volatilidad individual (eso es Inverse Volatility).
        """
    )

with st.form("portfolio_lab_form"):
    a, b, c = st.columns(3)
    pl_start = a.date_input("Inicio", value=date(2019, 1, 2), key="pl_start",
                            help="Recomendado: 2016-07-02 o después.")
    pl_end = b.date_input("Fin", value=date(2024, 1, 2), max_value=date.today(), key="pl_end")
    pl_interval = c.selectbox("Rebalanceo", [1, 3, 6, 12], index=1, format_func=lambda n: f"Cada {n} meses",
                              key="pl_interval")
    d, e = st.columns(2)
    pl_top_n = d.number_input("Nº de posiciones", 2, 50, 20, key="pl_top_n")
    pl_capital = e.number_input("Capital inicial ($)", 1_000, 10_000_000, 100_000, step=1_000, key="pl_capital")
    pl_schemes = st.multiselect(
        "Esquemas a comparar", list(pl.SCHEMES), default=list(pl.SCHEMES),
        format_func=lambda s: pl.SCHEME_LABELS[s], key="pl_schemes",
    )
    pl_mode = st.radio(
        "Modo", ["Validación (universo completo — lento)", "Desarrollo rápido (muestra)"],
        index=1, horizontal=True, key="pl_mode",
        help="Validación usa el universo histórico completo de cada fecha, sin muestrear — el único "
             "modo citable como evidencia. Puede tardar bastante más que un solo backtest V2: se "
             "calculan 6 esquemas de pesos por periodo.",
    )
    pl_max_symbols = None
    if pl_mode == "Desarrollo rápido (muestra)":
        pl_max_symbols = st.selectbox("Tamaño de la muestra", [50, 100, 200], index=1, key="pl_max_symbols")
    else:
        st.caption("⏱️ Puede tardar bastante en un rango de varios años — no se ha colgado.")
    if st.form_submit_button("Ejecutar Portfolio Lab"):
        if not pl_schemes:
            st.error("Selecciona al menos un esquema.")
        else:
            try:
                mode = "validation" if pl_mode.startswith("Validación") else "fast_dev"
                with st.spinner("Reconstruyendo rankings point-in-time y calculando los esquemas de pesos..."):
                    result = pl.run_portfolio_lab(
                        pl_start.isoformat(), pl_end.isoformat(), months=pl_interval, top_n=int(pl_top_n),
                        initial_capital=float(pl_capital), max_symbols=pl_max_symbols, mode=mode,
                        schemes=tuple(pl_schemes),
                    )
                st.session_state["portfolio_lab_result"] = result
            except (ValueError, RuntimeError) as exc:
                st.error(str(exc))

if "portfolio_lab_result" in st.session_state:
    result = st.session_state["portfolio_lab_result"]
    if result["skipped"]:
        with st.expander(f"⚠️ {len(result['skipped'])} periodo(s) saltado(s) por falta de cobertura"):
            st.dataframe(pd.DataFrame(result["skipped"]), hide_index=True, width="stretch")

    schemes_data = result["schemes"]

    st.subheader("Comparativa por esquema")
    rows = []
    for scheme, data in schemes_data.items():
        daily = data["daily"]
        rows.append({
            "Esquema": data["label"],
            "Retorno anualizado": daily["anualizado"],
            "Volatilidad anualizada": daily["vol_anualizada"],
            "Sharpe": daily["sharpe"],
            "Máx. drawdown": daily["max_drawdown"],
            "Turnover medio (%)": data["turnover_medio"],
            "Coste total ($)": data["comision_total"],
            "HHI": data["hhi"],
            "Top-3 contribution-to-risk": data["top3_contribution_to_risk"],
            "Tracking error vs SPY": data["tracking_error"],
        })
    table = pd.DataFrame(rows).set_index("Esquema")
    st.dataframe(
        table, width="stretch",
        column_config={
            "Retorno anualizado": st.column_config.NumberColumn(format="percent"),
            "Volatilidad anualizada": st.column_config.NumberColumn(format="percent"),
            "Sharpe": st.column_config.NumberColumn(format="%.2f"),
            "Máx. drawdown": st.column_config.NumberColumn(format="percent"),
            "Turnover medio (%)": st.column_config.NumberColumn(format="%.1f"),
            "Coste total ($)": st.column_config.NumberColumn(format="$%.0f"),
            "HHI": st.column_config.NumberColumn(format="%.3f"),
            "Top-3 contribution-to-risk": st.column_config.NumberColumn(format="percent"),
            "Tracking error vs SPY": st.column_config.NumberColumn(format="percent"),
        },
    )
    st.caption(
        "HHI (Herfindahl-Hirschman) = Σwᵢ² — 1/N es el mínimo posible con N posiciones (perfectamente "
        "equiponderado), 1.0 es todo en una sola posición. Top-3 contribution-to-risk = qué fracción de "
        "la VARIANZA total de la cartera (no del capital) explican las 3 posiciones con más riesgo, con "
        "los pesos del último rebalanceo."
    )

    st.subheader("Curvas de capital")
    with st.expander("Riesgo de cola · comparar esquemas y SPY"):
        tail_curves = {data["label"]: data["nav_curve"] for data in schemes_data.values()}
        tail_curves["SPY (buy & hold)"] = result["nav_curve_spy"]
        tail_risk_ui.render_nav(tail_curves, key="pl_tail")
    nav_table = pd.DataFrame({data["label"]: data["nav_curve"] for data in schemes_data.values()})
    nav_table["SPY (buy & hold)"] = result["nav_curve_spy"]
    st.line_chart(nav_table)

    st.subheader("Concentración del riesgo (último rebalanceo)")
    scheme_choice = st.selectbox("Esquema", list(schemes_data), format_func=lambda s: schemes_data[s]["label"],
                                 key="pl_scheme_risk")
    contrib = schemes_data[scheme_choice]["contribution_to_risk"]
    weights = schemes_data[scheme_choice]["last_weights"]
    if contrib:
        risk_df = pd.DataFrame({
            "Peso en $ (%)": pd.Series(weights),
            "Contribución al riesgo (%)": pd.Series(contrib),
        }).sort_values("Contribución al riesgo (%)", ascending=False)
        st.bar_chart(risk_df)
        st.dataframe(
            risk_df, width="stretch",
            column_config={
                "Peso en $ (%)": st.column_config.NumberColumn(format="percent"),
                "Contribución al riesgo (%)": st.column_config.NumberColumn(format="percent"),
            },
        )
        top3_symbols = risk_df.index[:3].tolist()
        top3_risk = risk_df["Contribución al riesgo (%)"].iloc[:3].sum()
        st.caption(f"Ejemplo concreto: **{', '.join(top3_symbols)}** juntas representan un "
                  f"**{top3_risk:.1%}** del riesgo total de esta cartera con {scheme_choice.replace('_', ' ')}.")
    else:
        st.info("Sin datos de covarianza suficientes para este esquema en el último rebalanceo.")

    st.subheader("Stress tests")
    st.warning(
        "⚠️ Esto **no son pronósticos** — son shocks arbitrarios aplicados con supuestos simples y "
        "explícitos, aplicados a los pesos del ÚLTIMO rebalanceo de cada esquema. Los escenarios con base "
        "🟢 usan beta/sector calculados de precios reales; los marcados ⚠️ usan una tabla de sensibilidad "
        "por sector **sin calibrar** (GABI no tiene datos de duración ni exposición a divisa por empresa) "
        "— trátalos como orientativos, no como una estimación seria.",
        icon="⚠️",
    )
    scenario_rows = []
    for scheme, data in schemes_data.items():
        row = {"Esquema": data["label"]}
        for sc in pl.SCENARIOS:
            outcome = result["scenarios"][scheme][sc]
            ground_icon = "🟢" if pl.SCENARIO_GROUND[sc] == "real" else "⚠️"
            label = f"{ground_icon} {pl.SCENARIO_LABELS[sc]}"
            if outcome["tipo"] == "volatilidad":
                row[label] = outcome["vol_escenario"]
            else:
                row[label] = outcome["impacto_pct"]
        scenario_rows.append(row)
    scenario_table = pd.DataFrame(scenario_rows).set_index("Esquema")
    st.dataframe(
        scenario_table, width="stretch",
        column_config={col: st.column_config.NumberColumn(format="percent") for col in scenario_table.columns},
    )
    st.caption("🟢 = base real (beta/sector de precios cacheados) · ⚠️ = heurística de manual sin calibrar. "
              "\"Volatilidad ×2\" muestra la volatilidad anualizada resultante, no un retorno.")
