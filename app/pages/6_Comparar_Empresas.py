import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from gabi import config, screener
from gabi.ui_helpers import METRIC_INFO, build_color_basis, format_metric_value, gradient_style, translate_sector

st.title("⚖️ Comparar empresas")
st.caption("Elige entre 2 y 5 empresas del universo analizado para verlas una junto a otra.")

# Paleta categórica validada (skill de dataviz) para gráficos de barras
# agrupadas con hasta 5 series: orden fijo, nunca reasignada por ranking.
SERIES_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
MAX_COMPANIES = 5

uni = screener.get_universe(limit=None)
weights = config.load_weights()
df = screener.build_screener_table(uni, weights=weights)

if df.empty:
    st.info("Todavía no hay datos. Ve a ⚙️ Configuración y pulsa 'Actualizar datos'.")
    st.stop()

options = df.index.tolist()


def _label(sym):
    row = df.loc[sym]
    return f"{sym} — {row.get('name')}"


default_selection = [s for s in st.session_state.get("compare_symbols", options[:2]) if s in options]

selected = st.multiselect(
    "Empresas a comparar", options, default=default_selection, format_func=_label,
    help=f"Selecciona entre 2 y {MAX_COMPANIES} empresas.",
)

if len(selected) > MAX_COMPANIES:
    st.warning(f"Máximo {MAX_COMPANIES} empresas a la vez — se usan las primeras {MAX_COMPANIES} seleccionadas.")
    selected = selected[:MAX_COMPANIES]
st.session_state["compare_symbols"] = selected

if len(selected) < 2:
    st.info("Selecciona al menos 2 empresas para compararlas.")
    st.stop()

subset = df.loc[selected]

st.subheader("Scores por bloque")
score_keys = ["value_score", "quality_score", "momentum_score", "risk_score", "composite_score"]
score_labels = [METRIC_INFO[k]["label"] for k in score_keys]

fig = go.Figure()
for i, sym in enumerate(selected):
    values = [subset.loc[sym, k] for k in score_keys]
    fig.add_trace(go.Bar(
        name=sym, x=score_labels, y=values,
        marker_color=SERIES_COLORS[i % len(SERIES_COLORS)],
        text=[f"{v:.0f}" if pd.notna(v) else "" for v in values],
        textposition="outside",
        cliponaxis=False,
    ))
fig.update_layout(
    barmode="group", height=420,
    yaxis=dict(range=[0, 108], title="Score (0-100, percentil vs. su sector)", gridcolor="#e1e0d9"),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    margin=dict(l=10, r=10, t=40, b=10), plot_bgcolor="rgba(0,0,0,0)",
)
st.plotly_chart(fig, width="stretch")
st.caption(
    "No hay un único 'ganador' — depende de qué te importe más: barata (Value), fundamentos (Quality), "
    "tendencia (Momentum) o riesgo bajo (Risk). El Composite es la media ponderada con tus pesos actuales."
)

st.divider()
st.subheader("Tabla comparativa")
st.caption(
    "🟩 mejor · 🟨 medio · 🟥 peor, comparado con el resto de empresas de su sector (no solo con las "
    "seleccionadas aquí). Para ver qué significa cada métrica, consulta 📊 Screener o 🔍 Ficha de empresa."
)

compare_keys = [
    "name", "sector", "market_cap", "pe", "peg", "roe", "roic", "revenue_growth_yoy",
    "revenue_cagr_3y", "debt_to_equity", "volatility", "max_drawdown", "sharpe_ratio",
    "price_vs_sma50", "momentum_6m", "rsi14",
    "value_score", "quality_score", "momentum_score", "risk_score", "composite_score",
]
present_keys = [k for k in compare_keys if k in subset.columns]
color_basis = build_color_basis(subset, present_keys)

def _format_cell(col, value):
    if col == "sector":
        return translate_sector(value) or "—"
    if col == "name":
        return value if pd.notna(value) else "—"
    return format_metric_value(col, value)


# Formateamos todo a texto ANTES de transponer: una tabla transpuesta con
# columnas de tipos mixtos (float en unas filas, str en otras) rompe la
# serialización a Arrow que usa Streamlit internamente.
table = pd.DataFrame(
    {col: subset[col].map(lambda v, c=col: _format_cell(c, v)) for col in present_keys},
    index=subset.index,
)

label_map = {k: METRIC_INFO[k]["label"] for k in present_keys}
table.rename(columns=label_map, inplace=True)
color_basis.rename(columns=label_map, inplace=True)
color_basis = color_basis.reindex(index=table.index, columns=table.columns)


def _apply_colors(_data):
    return color_basis.map(gradient_style)


styled = table.style.apply(_apply_colors, axis=None)
column_config = {
    label_map[k]: st.column_config.TextColumn(label_map[k], help=METRIC_INFO[k]["help"])
    for k in present_keys
}
st.dataframe(styled, width="stretch", height=min(500, 40 * (len(selected) + 1)), column_config=column_config)
