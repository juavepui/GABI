import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from gabi import config, screener, storage

st.set_page_config(page_title="Ficha de empresa — GABI", page_icon="🔍", layout="wide")
st.title("🔍 Ficha de empresa")

uni = screener.get_universe(limit=None)
weights = config.load_weights()
df = screener.build_screener_table(uni, weights=weights)

if df.empty:
    st.info("Todavía no hay datos. Ve a ⚙️ Configuración y pulsa 'Actualizar datos'.")
    st.stop()

default_symbol = st.session_state.get("selected_symbol", df.index[0])
symbol = st.selectbox(
    "Empresa", df.index.tolist(),
    index=df.index.get_loc(default_symbol) if default_symbol in df.index else 0,
)
st.session_state["selected_symbol"] = symbol

row = df.loc[symbol]

col_a, col_b, col_c, col_d = st.columns(4)
col_a.metric("Composite", f"{row['composite_score']:.1f}" if pd.notna(row["composite_score"]) else "—")
col_b.metric("Value", f"{row['value_score']:.1f}" if pd.notna(row["value_score"]) else "—")
col_c.metric("Quality", f"{row['quality_score']:.1f}" if pd.notna(row["quality_score"]) else "—")
col_d.metric("Momentum", f"{row['momentum_score']:.1f}" if pd.notna(row["momentum_score"]) else "—")

st.subheader(f"{row.get('name') or symbol} ({symbol}) — {row.get('sector') or 'Sector desconocido'}")

price_df = storage.get_prices(symbol)
if not price_df.empty:
    price_df = price_df.copy()
    price_df["sma50"] = price_df["close"].rolling(config.SMA_SHORT, min_periods=config.SMA_SHORT).mean()
    price_df["sma200"] = price_df["close"].rolling(config.SMA_LONG, min_periods=config.SMA_LONG).mean()

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=price_df.index, y=price_df["close"], name="Precio", line=dict(color="#2563eb")))
    fig.add_trace(go.Scatter(x=price_df.index, y=price_df["sma50"], name="SMA 50", line=dict(color="#f59e0b", dash="dot")))
    fig.add_trace(go.Scatter(x=price_df.index, y=price_df["sma200"], name="SMA 200", line=dict(color="#dc2626", dash="dot")))
    fig.update_layout(height=420, margin=dict(l=10, r=10, t=30, b=10), legend=dict(orientation="h"))
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Sin histórico de precios cacheado para esta empresa todavía.")

st.divider()
st.subheader("Desglose del score (por qué puntúa así)")

from gabi import scoring  # noqa: E402  (import tardío para evitar coste si no se usa)

breakdown = scoring.explain_row(df, symbol)
if not breakdown.empty:
    breakdown = breakdown.dropna(subset=["value"])
    breakdown["percentile"] = breakdown["percentile"].round(1)
    st.dataframe(breakdown, use_container_width=True, hide_index=True)
else:
    st.info("Sin métricas disponibles para el desglose.")

st.caption(
    "El percentil indica la posición de la empresa dentro del universo analizado "
    "para esa métrica (100 = mejor, 0 = peor), ya invertido cuando 'menos es mejor' "
    "(ej. PER, deuda)."
)
