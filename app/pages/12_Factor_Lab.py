import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import pandas as pd
import streamlit as st

from gabi import factor_lab

st.title("📐 Factor Lab")
st.caption(
    "En vez de \"¿el Top-20 ganó al SPY?\", una pregunta más informativa: **¿el score contiene "
    "información predictiva de forma gradual y consistente?** Cada rebalanceo, el universo se divide en "
    "quintiles por score (Q1 peor → Q5 mejor) y se mide el retorno FUTURO real a 1/3/6/12 meses — si el "
    "score es bueno, Q1 < Q2 < Q3 < Q4 < Q5 de forma razonablemente consistente, no solo en la cesta "
    "concreta que se eligió."
)

with st.expander("ℹ️ Qué es Rank IC / ICIR (léelo si no los conoces)"):
    st.markdown(
        """
- **Rank IC** (Information Coefficient, correlación de Spearman): de -1 a +1, cuánto ordena el score el
  retorno futuro REAL de cada empresa ese periodo. 0 = el score no dice nada sobre quién sube más;
  cerca de +1 = ordena casi perfectamente.
- **ICIR**: el IC medio dividido entre su desviación típica a lo largo del tiempo — mide si el IC es
  **consistente** periodo a periodo, no solo si es alto de media (un IC medio decente pero muy errático
  vale menos que uno más modesto pero estable).
- **Sector-neutral**: el retorno de cada empresa se compara contra la media de SU sector ese periodo
  antes de calcular el IC — aísla si el score elige ganadores DENTRO de su sector, o si solo capta qué
  sector estuvo de moda ese trimestre (que no es mérito del score).
- **Turnover del quintil**: qué fracción de las empresas de un quintil son nuevas respecto al rebalanceo
  anterior — un quintil con mucho turnover es más caro de replicar en la práctica.
        """
    )

with st.form("factor_lab_form"):
    a, b, c = st.columns(3)
    fl_start = a.date_input("Inicio", value=date(2019, 1, 2), key="fl_start",
                            help="Recomendado: 2016-07-02 o después.")
    fl_end = b.date_input("Fin", value=date(2024, 1, 2), max_value=date.today(), key="fl_end")
    fl_interval = c.selectbox("Rebalanceo", [1, 3, 6, 12], index=1, format_func=lambda n: f"Cada {n} meses",
                              key="fl_interval")
    fl_mode = st.radio(
        "Modo", ["Validación (universo completo — lento)", "Desarrollo rápido (muestra)"],
        index=1, horizontal=True, key="fl_mode",
        help="Validación usa el universo histórico completo de cada fecha, sin muestrear — el único "
             "modo citable como evidencia. Puede tardar 20-30 minutos en un rango de varios años.",
    )
    fl_max_symbols = None
    if fl_mode == "Desarrollo rápido (muestra)":
        fl_max_symbols = st.selectbox("Tamaño de la muestra", [50, 100, 200], index=2, key="fl_max_symbols")
    else:
        st.caption("⏱️ Puede tardar 20-30 minutos en un rango de varios años — no se ha colgado.")
    if st.form_submit_button("Ejecutar Factor Lab"):
        try:
            mode = "validation" if fl_mode.startswith("Validación") else "fast_dev"
            result = factor_lab.run_factor_analysis(
                fl_start.isoformat(), fl_end.isoformat(), months=fl_interval,
                max_symbols=fl_max_symbols, mode=mode,
            )
            st.session_state["factor_lab_result"] = result
        except (ValueError, RuntimeError) as exc:
            st.error(str(exc))

if "factor_lab_result" in st.session_state:
    result = st.session_state["factor_lab_result"]
    if result["skipped"]:
        with st.expander(f"⚠️ {len(result['skipped'])} periodo(s) saltado(s) por falta de cobertura"):
            st.dataframe(pd.DataFrame(result["skipped"]), hide_index=True, width="stretch")

    summary = result["summary"]
    turnover = result["turnover"]
    if summary.empty:
        st.warning("Ningún factor tuvo suficientes datos para analizarse en este rango.")
        st.stop()

    sector_neutral_view = st.checkbox("Vista sector-neutral", value=False,
                                      help="Retornos comparados contra la media de su sector antes de calcular el IC.")

    view = summary[summary["sector_neutral"] == sector_neutral_view]
    horizons = sorted(view["horizonte"].unique())
    pivot_ic = view.pivot_table(index="factor", columns="horizonte", values="ic_mean")
    pivot_ic.columns = [f"IC {h}m" for h in pivot_ic.columns]
    factor_table = pivot_ic.copy()
    factor_table["Estabilidad (ICIR medio)"] = view.groupby("factor")["icir"].mean()
    factor_table["Q_máx−Q1 medio"] = view.groupby("factor")["q_spread"].mean()
    if not turnover.empty:
        factor_table["Turnover medio"] = turnover.groupby("factor")["turnover"].mean()
    factor_table = factor_table.reset_index().rename(columns={"factor": "Factor"})

    st.subheader("Resumen por factor" + (" (sector-neutral)" if sector_neutral_view else ""))
    st.dataframe(
        factor_table, hide_index=True, width="stretch",
        column_config={col: st.column_config.NumberColumn(format="%.3f")
                      for col in factor_table.columns if col != "Factor"},
    )
    st.caption(
        "Puede perfectamente ocurrir que un bloque no aporte prácticamente nada (IC≈0 en todos los "
        "horizontes) — eso es información tan valiosa como encontrar uno que sí funcione."
    )

    st.subheader("Decay del IC por horizonte")
    ic_decay = view.pivot_table(index="horizonte", columns="factor", values="ic_mean")
    st.line_chart(ic_decay)
    st.caption("IC medio a cada horizonte, por factor — si un factor decae rápido hacia 0, su información "
              "predictiva es de corto plazo.")

    st.subheader("Retorno medio por quintil")
    qc1, qc2 = st.columns(2)
    factor_choice = qc1.selectbox("Factor", sorted(view["factor"].unique()), key="fl_factor_choice")
    horizon_choice = qc2.selectbox("Horizonte (meses)", horizons, key="fl_horizon_choice")
    qret = result["quantile_returns"]
    q_col = "retorno_medio_neutral" if sector_neutral_view else "retorno_medio"
    q_view = qret[(qret["factor"] == factor_choice) & (qret["horizonte"] == horizon_choice)]
    if q_view.empty:
        st.info("Sin datos suficientes para esta combinación de factor/horizonte.")
    else:
        by_quantile = q_view.groupby("quantil")[q_col].mean()
        st.bar_chart(by_quantile)
        st.caption("Q1 = peor score, Q_máx = mejor score — si el modelo funciona, debería subir de "
                  "izquierda a derecha, no necesariamente en línea recta.")
