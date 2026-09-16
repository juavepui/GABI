import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import streamlit as st

from gabi import config, screener

st.set_page_config(page_title="Screener — GABI", page_icon="📊", layout="wide")
st.title("📊 Screener")

DISPLAY_COLS = {
    "name": "Empresa", "sector": "Sector", "market_cap": "Cap. mercado",
    "pe": "PER", "roe": "ROE", "revenue_growth_yoy": "Crec. ingresos YoY",
    "price": "Precio", "price_vs_sma50": "vs SMA50", "rsi14": "RSI14",
    "value_score": "Value", "quality_score": "Quality", "momentum_score": "Momentum",
    "composite_score": "Composite",
}

saved_weights = config.load_weights()

with st.sidebar:
    st.header("Pesos del score")
    w_value = st.slider("Value", 0, 100, int(saved_weights.get("value", 0.35) * 100))
    w_quality = st.slider("Quality", 0, 100, int(saved_weights.get("quality", 0.35) * 100))
    w_momentum = st.slider("Momentum", 0, 100, int(saved_weights.get("momentum", 0.30) * 100))
    total_w = max(w_value + w_quality + w_momentum, 1)
    weights = {"value": w_value / total_w, "quality": w_quality / total_w, "momentum": w_momentum / total_w}

    st.header("Filtros")
    min_market_cap_b = st.number_input("Cap. de mercado mínima (miles de millones $)", min_value=0.0, value=0.0, step=1.0)
    only_golden_cross = st.checkbox("Solo con golden cross reciente", value=False)
    hide_no_data = st.checkbox("Ocultar empresas sin datos descargados", value=True)

uni = screener.get_universe(limit=None)
df = screener.build_screener_table(uni, weights=weights)

if df.empty:
    st.info("Todavía no hay datos. Ve a ⚙️ Configuración y pulsa 'Actualizar datos'.")
    st.stop()

filtered = df.copy()
if hide_no_data:
    filtered = filtered[filtered["price"].notna() | filtered["pe"].notna()]
if min_market_cap_b > 0:
    filtered = filtered[filtered["market_cap"].fillna(0) >= min_market_cap_b * 1e9]
if only_golden_cross:
    filtered = filtered[filtered["golden_cross_recent"] == True]  # noqa: E712

if "sector" in filtered.columns:
    sectors = sorted([s for s in filtered["sector"].dropna().unique()])
    with st.sidebar:
        selected_sectors = st.multiselect("Sector", sectors, default=[])
    if selected_sectors:
        filtered = filtered[filtered["sector"].isin(selected_sectors)]

st.caption(f"{len(filtered)} empresas (de {len(df)} en el universo analizado)")

display_df = filtered[[c for c in DISPLAY_COLS if c in filtered.columns]].rename(columns=DISPLAY_COLS)
for score_col in ["Value", "Quality", "Momentum", "Composite"]:
    if score_col in display_df.columns:
        display_df[score_col] = display_df[score_col].round(1)

st.dataframe(display_df, use_container_width=True, height=500)

st.divider()
st.subheader("Ver ficha de una empresa")
options = filtered.index.tolist()
if options:
    def _label(sym):
        row = filtered.loc[sym]
        score = row.get("composite_score")
        score_txt = f" (Composite: {score:.1f})" if score == score else ""  # NaN != NaN
        return f"{sym} — {row.get('name')}{score_txt}"

    selected = st.selectbox("Empresa", options, format_func=_label)
    if st.button("Ver ficha →"):
        st.session_state["selected_symbol"] = selected
        st.switch_page("pages/2_Ficha_Empresa.py")
