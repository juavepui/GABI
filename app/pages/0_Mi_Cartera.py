import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import pandas as pd
import streamlit as st

from gabi import app_mode, screener, simple_portfolio
from gabi.ui_helpers import translate_sector

st.title("🎯 Mi cartera")
st.caption(
    "La respuesta directa a \"¿qué compro?\": aplica exactamente la hipótesis ya validada con backtest "
    f"histórico ({app_mode.FROZEN_LABEL}) — Top-N equiponderado, pesos Value 30% · Quality 35% · "
    "Momentum 25% · Risk 10%. Sin configuración que ajustar. Si quieres experimentar con otros pesos, "
    "reglas de riesgo u optimización de cartera, esa es la función de 🧭 Decisiones de cartera y del modo "
    "Research."
)
st.warning(
    "⚠️ No es asesoramiento financiero ni una orden de compra — son reglas mecánicas aplicadas al ranking "
    "de hoy. Verifica siempre antes de invertir dinero real.",
    icon="⚠️",
)

uni = screener.get_universe(limit=None)
with st.spinner(f"Cargando {len(uni)} empresas del universo..."):
    load_bar = st.progress(0.0)

    def _load_progress(done, total):
        load_bar.progress(done / total if total else 1.0)

    df = screener.build_screener_table(uni, weights=app_mode.FROZEN_WEIGHTS, progress_cb=_load_progress)
    load_bar.empty()

if df.empty:
    st.info("Todavía no hay datos. Ve a ⚙️ Configuración y pulsa 'Actualizar datos'.")
    st.stop()

if simple_portfolio.eligible_candidates(df).empty:
    st.warning("Ninguna empresa cumple hoy la cobertura mínima de datos (70%) para entrar en el ranking. "
              "Actualiza datos en ⚙️ Configuración.")
    st.stop()

n_positions = st.slider(
    "Número de posiciones", min_value=5, max_value=30, value=20,
    help="La hipótesis validada usa 20 — es la única cifra con un backtest histórico real detrás. Puedes "
         "ver menos si prefieres una cartera más concentrada; siguen siendo las mejores por Composite Score.",
)
if n_positions != 20:
    st.caption(f"ℹ️ Estás viendo el Top-{n_positions}, no el Top-20 validado.")

ranked = simple_portfolio.target_portfolio(df, n_positions)
capital = st.number_input("Capital a invertir (€)", min_value=0.0, value=1000.0, step=100.0)

target = ranked[["name", "sector", "composite_score", "confidence", "price", "weight_pct"]].copy()
target["sector"] = target["sector"].map(translate_sector)
target["Importe (€)"] = capital * target["weight_pct"] / 100
target["Acciones aprox."] = (target["Importe (€)"] / target["price"]).where(target["price"] > 0)
target = target.reset_index().rename(columns={
    "symbol": "Símbolo", "name": "Empresa", "sector": "Sector",
    "composite_score": "Composite Score", "confidence": "Confidence", "price": "Precio",
    "weight_pct": "Peso (%)",
})

st.subheader(f"Tu cartera objetivo — {len(ranked)} posiciones, {ranked['weight_pct'].iloc[0]:.1f}% cada una")
st.dataframe(
    target[["Símbolo", "Empresa", "Sector", "Composite Score", "Confidence", "Precio",
           "Peso (%)", "Importe (€)", "Acciones aprox."]],
    hide_index=True, width="stretch",
    column_config={
        "Composite Score": st.column_config.NumberColumn(format="%.1f"),
        "Confidence": st.column_config.NumberColumn(format="%.0f"),
        "Precio": st.column_config.NumberColumn(format="%.2f"),
        "Peso (%)": st.column_config.NumberColumn(format="%.1f%%"),
        "Importe (€)": st.column_config.NumberColumn(format="%.2f €"),
        "Acciones aprox.": st.column_config.NumberColumn(format="%.2f"),
    },
)
st.caption(
    "\"Acciones aprox.\" asume que tu bróker permite acciones fraccionadas (eToro sí) — si no, redondea "
    "hacia abajo. Rebalanceo pensado trimestral, como en la hipótesis congelada — no hace falta volver "
    "cada día a mirar esta lista."
)

st.divider()
st.subheader("¿Dónde meto mi próximo dinero?")
st.caption(
    "Si ya tienes posiciones abiertas, dinos cuánto llevas invertido en cada una (en €) y cuánto capital "
    "nuevo quieres meter ahora — te decimos qué comprar primero para acercarte al objetivo de arriba, "
    "priorizando lo que más te falta. No calcula ventas: eso depende de tu fiscalidad y de tu propia tesis."
)
holdings_text = st.text_area(
    "Tus posiciones actuales (símbolo, € invertidos; una por línea — déjalo vacío si empiezas de cero)",
    placeholder="AAPL,300\nMSFT,200", height=100,
)
new_capital = st.number_input("Capital nuevo a invertir ahora (€)", min_value=0.0, value=1000.0,
                              step=100.0, key="new_capital")

if st.button("Calcular dónde invertir", type="primary"):
    try:
        current = simple_portfolio.parse_holdings(holdings_text)
    except ValueError as exc:
        st.error(str(exc))
    else:
        result = simple_portfolio.allocate_new_capital(ranked, current, new_capital)
        if not result["allocations"]:
            st.info("Ya estás en (o por encima de) el objetivo en todas las posiciones que puedes cubrir "
                    "con este capital — nada urgente que comprar ahora mismo.")
        else:
            alloc_df = pd.DataFrame(result["allocations"]).rename(
                columns={"symbol": "Símbolo", "name": "Empresa", "amount": "Importe (€)"})
            st.dataframe(alloc_df, hide_index=True, width="stretch",
                        column_config={"Importe (€)": st.column_config.NumberColumn(format="%.2f €")})
            if result["remaining"] > 0.01:
                st.caption(f"Con esto ya cubres el objetivo en tus posiciones más infraponderadas — te "
                          f"sobran {result['remaining']:.2f} € que podrías repartir a partes iguales entre "
                          f"las {len(ranked)} posiciones para mantener el equilibrio.")

        if result["outside_target"]:
            st.warning(
                "Estas posiciones que ya tienes no están en el Top actual — no es una recomendación de "
                "venta (depende de tu fiscalidad y de tu tesis), solo un aviso de que ya no forman parte "
                "del ranking objetivo: " + ", ".join(result["outside_target"])
            )
