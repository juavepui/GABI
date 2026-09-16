import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from gabi import ai_prompt, config, scoring, screener, storage
from gabi.ui_helpers import METRIC_INFO, format_metric_value, gradient_style, translate_sector

st.title("🔍 Ficha de empresa")

uni = screener.get_universe(limit=None)
weights = config.load_weights()
df = screener.build_screener_table(uni, weights=weights)

if df.empty:
    st.info("Todavía no hay datos. Ve a ⚙️ Configuración y pulsa 'Actualizar datos'.")
    st.stop()

default_symbol = st.session_state.get("selected_symbol", df.index[0])


def _label(sym):
    return f"{sym} — {df.loc[sym, 'name']}" if pd.notna(df.loc[sym, "name"]) else sym


symbol = st.selectbox(
    "Empresa", df.index.tolist(),
    index=df.index.get_loc(default_symbol) if default_symbol in df.index else 0,
    format_func=_label,
    help="Busca por ticker o por nombre de la empresa.",
)
st.session_state["selected_symbol"] = symbol

row = df.loc[symbol]

col_a, col_b, col_c, col_d, col_e = st.columns(5)
col_a.metric("Composite", f"{row['composite_score']:.1f}" if pd.notna(row["composite_score"]) else "—", help=METRIC_INFO["composite_score"]["help"])
col_b.metric("Value", f"{row['value_score']:.1f}" if pd.notna(row["value_score"]) else "—", help=METRIC_INFO["value_score"]["help"])
col_c.metric("Quality", f"{row['quality_score']:.1f}" if pd.notna(row["quality_score"]) else "—", help=METRIC_INFO["quality_score"]["help"])
col_d.metric("Momentum", f"{row['momentum_score']:.1f}" if pd.notna(row["momentum_score"]) else "—", help=METRIC_INFO["momentum_score"]["help"])
col_e.metric("Risk", f"{row['risk_score']:.1f}" if pd.notna(row["risk_score"]) else "—", help=METRIC_INFO["risk_score"]["help"])

sector_es = translate_sector(row.get("sector")) or "Sector desconocido"
title_col, action_col = st.columns([4, 1])
title_col.subheader(f"{row.get('name') or symbol} ({symbol}) — {sector_es}")
if action_col.button("📝 Escribir tesis", help="Abre el Diario de inversión con esta empresa precargada."):
    st.session_state["journal_prefill_symbol"] = symbol
    st.switch_page("pages/4_Diario_Inversion.py")

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
    st.plotly_chart(fig, width="stretch")
    st.caption(
        "**SMA 50 / SMA 200**: medias móviles de 50 y 200 sesiones — suavizan el precio para ver la "
        "tendencia de corto y largo plazo. Cuando la SMA 50 cruza por encima de la SMA 200 se le llama "
        "*golden cross*, una señal técnica alcista clásica."
    )
else:
    st.info("Sin histórico de precios cacheado para esta empresa todavía.")

st.divider()
st.subheader("📐 Otras métricas (informativas, no puntuadas)")
st.caption(
    "No entran en el Composite Score — contexto adicional inspirado en las métricas típicas de "
    "análisis de carteras (Sharpe, Sortino, beta...) aplicadas a esta empresa concreta."
)
info_metrics = ["beta_calc", "alpha", "win_rate_monthly", "beta", "dividend_yield", "avg_volume"]
info_cols = st.columns(3)
for i, key in enumerate(info_metrics):
    col = info_cols[i % 3]
    col.metric(
        METRIC_INFO[key]["label"], format_metric_value(key, row.get(key)),
        help=METRIC_INFO[key]["help"],
    )

has_10k = pd.notna(row.get("latest_10k_url"))
has_10q = pd.notna(row.get("latest_10q_url"))
if has_10k or has_10q:
    st.divider()
    st.subheader("📄 Informes oficiales (SEC EDGAR)")
    st.caption(
        "Antes de invertir, ábrelos y lee de dónde sale y adónde va el dinero — no hace falta "
        "convertirse en contable, pero sí entender las cuentas reales, no solo el score."
    )
    fcol1, fcol2 = st.columns(2)
    if has_10k:
        fcol1.link_button(f"📘 Último 10-K ({row.get('latest_10k_date')})", row["latest_10k_url"])
    if has_10q:
        fcol2.link_button(f"📗 Último 10-Q ({row.get('latest_10q_date')})", row["latest_10q_url"])

st.divider()
st.subheader("Desglose del score (por qué puntúa así)")
st.caption(
    "El percentil compara la empresa **con otras de su mismo sector** cuando hay suficientes (si no, "
    "usa todo el universo analizado): 100 = mejor, 0 = peor, ya invertido cuando 'menos es mejor' "
    "(ej. PER, deuda). El color sigue el mismo criterio: 🟩 mejor · 🟨 medio · 🟥 peor."
)

breakdown = scoring.explain_row(df, symbol)
if not breakdown.empty:
    breakdown = breakdown.dropna(subset=["value"]).copy()
    breakdown["Métrica"] = breakdown["metric"].map(lambda m: METRIC_INFO.get(m, {}).get("label", m))
    breakdown["Valor"] = breakdown.apply(lambda r: format_metric_value(r["metric"], r["value"]), axis=1)
    breakdown["Percentil"] = breakdown["percentile"].round(1)
    breakdown["Qué significa"] = breakdown["metric"].map(lambda m: METRIC_INFO.get(m, {}).get("help", ""))
    display_breakdown = breakdown[["Métrica", "Valor", "Percentil", "Qué significa"]].reset_index(drop=True)

    def _style_percentile(row_):
        return ["" if col != "Percentil" else gradient_style(row_["Percentil"]) for col in display_breakdown.columns]

    styled_breakdown = display_breakdown.style.apply(_style_percentile, axis=1)
    st.dataframe(
        styled_breakdown, width="stretch", hide_index=True,
        column_config={
            "Qué significa": st.column_config.TextColumn("Qué significa", width="large"),
        },
    )
else:
    st.info("Sin métricas disponibles para el desglose.")

st.divider()
st.subheader("🤖 Prompt para analizar con IA")
st.caption(
    "Pensado para pegarlo en el asistente que prefieras (Claude, ChatGPT...). No le pide que "
    "prediga el precio: le da los números que GABI ya ha calculado y le pide interpretarlos junto "
    "a los documentos que le pegues (earnings call, guidance, noticias). **Regla de diseño: la IA "
    "nunca calcula métricas financieras — los números vienen siempre de aquí, no se los inventa.**"
)
prompt_text = ai_prompt.build_analysis_prompt(row, breakdown, symbol)
st.code(prompt_text, language=None, wrap_lines=True)
st.caption(
    "Usa el icono de copiar de la esquina superior derecha del recuadro. Antes de pegarlo, añade el "
    "texto de la earnings call, el guidance y las noticias relevantes donde el prompt lo indica — "
    "sin eso, la IA solo podrá trabajar con los números y los enlaces a los informes oficiales."
)
