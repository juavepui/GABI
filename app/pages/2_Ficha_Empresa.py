import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from gabi import ai_prompt, config, events_calendar, filing_tracker, insider, scoring, screener, storage
from gabi.ui_helpers import METRIC_INFO, format_metric_value, gradient_style, translate_sector

st.title("🔍 Ficha de empresa")

uni = screener.get_universe(limit=None)
weights = config.load_weights()
with st.spinner(f"Cargando {len(uni)} empresas del universo..."):
    load_bar = st.progress(0.0)

    def _load_progress(done, total):
        load_bar.progress(done / total if total else 1.0)

    df = screener.build_screener_table(uni, weights=weights, progress_cb=_load_progress)
    load_bar.empty()

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

col_a, col_b, col_c, col_d, col_e, col_f = st.columns(6)
col_a.metric("Composite", f"{row['composite_score']:.1f}" if pd.notna(row["composite_score"]) else "—", help=METRIC_INFO["composite_score"]["help"])
col_b.metric("Value", f"{row['value_score']:.1f}" if pd.notna(row["value_score"]) else "—", help=METRIC_INFO["value_score"]["help"])
col_c.metric("Quality", f"{row['quality_score']:.1f}" if pd.notna(row["quality_score"]) else "—", help=METRIC_INFO["quality_score"]["help"])
col_d.metric("Momentum", f"{row['momentum_score']:.1f}" if pd.notna(row["momentum_score"]) else "—", help=METRIC_INFO["momentum_score"]["help"])
col_e.metric("Risk", f"{row['risk_score']:.1f}" if pd.notna(row["risk_score"]) else "—", help=METRIC_INFO["risk_score"]["help"])
col_f.metric("Confidence", f"{row['confidence']:.0f}" if pd.notna(row.get("confidence")) else "—", help=METRIC_INFO["confidence"]["help"])

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
st.subheader("📅 Próximos catalizadores")
st.caption(
    "Fechas conocidas, no una predicción de qué va a pasar con el precio -- contexto temporal para no "
    "llegar a un buen score sin saber que tiene earnings mañana. No entra en el Composite Score."
)
fundamentals_record = storage.get_fundamentals([symbol]).get(symbol, {})
upcoming = events_calendar.parse_corporate_events(
    symbol, fundamentals_record.get("info", {}), fundamentals_record.get("fetched_at", ""),
)
future_events = [e for e in upcoming if e["days_until"] >= 0]
if future_events:
    for e in sorted(future_events, key=lambda e: e["event_date"]):
        confirmed_label = "estimada" if e["is_estimate"] else "confirmada"
        st.caption(
            f"🗓️ **{events_calendar.EVENT_LABELS[e['event_type']]}**: {e['event_date'].isoformat()}"
            + (f" – {e['range_end'].isoformat()}" if e["range_end"] else "")
            + f" (fecha {confirmed_label}, en {e['days_until']} días) · fuente: {e['source']}"
        )
else:
    st.caption("Sin próximos eventos conocidos en los datos cacheados de Yahoo Finance para esta empresa.")

with st.expander("📊 Historial de sorpresas de resultados (dato de investigación, no puntuado)"):
    st.caption(
        "EPS estimado vs reportado y el gap de precio entre el cierre anterior y el posterior al earnings "
        "-- se guarda para poder validarlo algún día en 🔬 Research Lab / 📐 Factor Lab como factor "
        "candidato. Hoy NO influye en el Composite Score de ninguna manera."
    )
    if st.button("🔄 Sincronizar historial de earnings de esta empresa"):
        with st.spinner("Descargando earnings_dates de Yahoo Finance..."):
            sync_failed = events_calendar.sync_earnings_surprises([symbol])
        if sync_failed:
            st.error(f"No se pudo sincronizar: {sync_failed.get(symbol)}")
        else:
            st.success("Sincronizado.")
            st.rerun()
    surprises = events_calendar.get_earnings_surprises(symbol)
    if surprises.empty:
        st.caption("Sin historial sincronizado todavía -- pulsa el botón de arriba.")
    else:
        display_surprises = surprises[[
            "earnings_date", "eps_estimate", "eps_reported", "surprise_pct", "price_reaction_pct",
        ]].copy()
        display_surprises.columns = ["Fecha", "EPS estimado", "EPS reportado", "Sorpresa %", "Reacción precio %"]
        st.dataframe(display_surprises, hide_index=True, width="stretch")

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

    st.markdown("**Qué cambió respecto al filing anterior**")
    st.caption(
        "\"Cambio material\" es una regla explícita de GABI (umbrales de % o puntos porcentuales sobre "
        "cada métrica), no una conclusión de inversión -- exactamente igual que el Composite Score. "
        "Compara solo métricas fundamentales ya parseadas (ingresos, márgenes, FCF, deuda, caja, ROIC); "
        "no analiza el texto del filing (Risk Factors, MD&A) todavía."
    )
    METRIC_LABELS_FILING = {
        "revenue": "Ingresos", "operating_margin": "Margen operativo", "gross_margin": "Margen bruto",
        "fcf": "Flujo de caja libre", "debt": "Deuda a largo plazo", "cash": "Caja", "roic": "ROIC",
    }
    for form in [f for f, has in (("10-K", has_10k), ("10-Q", has_10q)) if has]:
        filing_result = filing_tracker.compare_filings(symbol, form)
        if filing_result["previous"] is not None:
            expander_label = f"{form}: {filing_result['previous']['filed_date']} → {filing_result['current']['filed_date']}"
        else:
            expander_label = f"{form}: {filing_result['reason']}"
        with st.expander(expander_label):
            if not filing_result["rows"]:
                st.caption(filing_result["reason"])
                continue
            change_rows = [
                {
                    "Métrica": METRIC_LABELS_FILING.get(r["metric"], r["metric"]),
                    "Anterior": r["previous_value"], "Actual": r["current_value"],
                    "Cambio": f"{r['pct_change']:+.1%}" if r["pct_change"] is not None else f"{r['abs_change']:+.2f}",
                    "Evaluación": {"improvement": "🟢 mejora", "deterioration": "🔴 deterioro",
                                  "stable": "⚪ estable"}[r["direction"]],
                }
                for r in filing_result["rows"]
            ]
            st.dataframe(pd.DataFrame(change_rows), hide_index=True, width="stretch")

st.divider()
st.subheader("🕵️ Actividad de insiders (SEC Form 4)")
st.caption(
    "Compras y ventas de directivos/consejeros con sus propias acciones. Una compra en mercado "
    "abierto (código P) fuera de un plan 10b5-1 preprogramado es la señal más informativa que hay "
    "aquí — ventas y ejercicios de opciones son mucho más rutinarios (compensación, impuestos) y "
    "dicen poco por sí solos. Informativo: no entra en el Composite Score."
)
if st.button("🔄 Actualizar insiders de esta empresa", help="Descarga los últimos Form 4 de SEC EDGAR para este símbolo."):
    with st.spinner("Descargando Form 4 de SEC EDGAR..."):
        insider_result = insider.ensure_insider_data([symbol], max_age_hours=0)
    if insider_result["failed"]:
        st.error(f"No se pudo actualizar: {insider_result['failed'].get(symbol)}")
    else:
        st.success("Actualizado.")
        st.rerun()

insider_summary = insider.summarize_insider_activity(symbol, months=6)
ic1, ic2, ic3 = st.columns(3)
ic1.metric(
    "Compras (6 meses)", insider_summary["n_buys"],
    help="Compras en mercado abierto (código P) de directivos/consejeros/accionistas >10%. No incluye ejercicios de opciones ni concesiones.",
)
ic2.metric("Ventas (6 meses)", insider_summary["n_sells"], help="Ventas en mercado abierto (código S).")
net_value = insider_summary["net_value"]
ic3.metric(
    "Neto comprado − vendido", f"${net_value:,.0f}" if net_value is not None else "—",
    help="Valor de las compras menos el de las ventas en mercado abierto, en los últimos 6 meses.",
)
if insider_summary["n_buys"] > 0 and insider_summary["has_10b5_1_only_buys"]:
    st.caption("⚠️ Todas las compras recientes son de un plan 10b5-1 preprogramado — mucho menos informativas que una compra discrecional decidida ahora.")

recent_tx = insider_summary["recent"]
if not recent_tx.empty:
    display_tx = recent_tx[[
        "transaction_date", "owner_name", "owner_title", "transaction_code",
        "shares", "price_per_share", "is_10b5_1_plan",
    ]].copy()
    display_tx["transaction_code"] = display_tx["transaction_code"].map(lambda c: insider.TRANSACTION_CODES.get(c, c))
    display_tx["is_10b5_1_plan"] = display_tx["is_10b5_1_plan"].map({1: "Sí", 0: "No"})
    display_tx.columns = ["Fecha", "Insider", "Cargo", "Operación", "Acciones", "Precio", "¿Plan 10b5-1?"]
    st.dataframe(display_tx, hide_index=True, width="stretch")
else:
    st.info(
        "Sin operaciones de insiders en los últimos 6 meses cacheadas para esta empresa — pulsa "
        "'Actualizar insiders de esta empresa' arriba."
    )

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
    # st.dataframe trunca el texto de cada celda sin posibilidad de ajuste de línea
    # (comprobado: "Qué significa" se cortaba) — st.table no trunca, crece con el
    # contenido, y sigue soportando el Styler para el color del percentil.
    st.table(styled_breakdown, hide_index=True)
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
