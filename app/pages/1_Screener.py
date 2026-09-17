import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import streamlit as st

from gabi import config, evaluation, screener
from gabi.ui_helpers import FRACTION_COLUMNS, METRIC_INFO, build_color_basis, gradient_style, translate_sector

st.title("📊 Screener")
st.caption(
    "Los colores indican la posición de cada empresa **dentro de su sector** para esa métrica "
    "(comparar el PER de un banco con el de una tecnológica no tiene sentido): 🟩 mejor · 🟨 medio · "
    "🟥 peor. Pasa el ratón sobre el nombre de cada columna para ver qué significa."
)

# Columnas que se muestran en la tabla, en orden.
DISPLAY_KEYS = [
    "name", "sector", "market_cap", "pe", "roe", "roic", "revenue_growth_yoy",
    "price", "price_vs_sma50", "rsi14", "volatility", "max_drawdown",
    "metrics_available", "metrics_possible", "score_coverage",
    "value_score", "quality_score", "momentum_score", "risk_score", "composite_score",
]

saved_weights = config.load_weights()

with st.sidebar:
    st.header("Pesos del score")
    st.caption(
        "💡 Si estás empezando, considera dar más peso a Value y Quality que a Momentum: "
        "los fundamentos importan más que los indicadores técnicos al principio."
    )
    w_value = st.slider("Value", 0, 100, int(saved_weights.get("value", 0.30) * 100), help=METRIC_INFO["value_score"]["help"])
    w_quality = st.slider("Quality", 0, 100, int(saved_weights.get("quality", 0.35) * 100), help=METRIC_INFO["quality_score"]["help"])
    w_momentum = st.slider("Momentum", 0, 100, int(saved_weights.get("momentum", 0.25) * 100), help=METRIC_INFO["momentum_score"]["help"])
    w_risk = st.slider("Risk", 0, 100, int(saved_weights.get("risk", 0.10) * 100), help=METRIC_INFO["risk_score"]["help"])
    total_w = max(w_value + w_quality + w_momentum + w_risk, 1)
    weights = {
        "value": w_value / total_w, "quality": w_quality / total_w,
        "momentum": w_momentum / total_w, "risk": w_risk / total_w,
    }

    st.header("Filtros")
    search_query = st.text_input(
        "🔎 Buscar empresa", value="",
        placeholder="Nombre o ticker (ej. Apple, AAPL)",
        help="Filtra por coincidencia parcial en el nombre o el símbolo de la empresa.",
    )
    min_market_cap_b = st.number_input(
        "Cap. de mercado mínima (miles de millones $)", min_value=0.0, value=0.0, step=1.0,
        help="Oculta empresas con capitalización de mercado por debajo de este umbral.",
    )
    only_golden_cross = st.checkbox(
        "Solo con golden cross reciente", value=False, help=METRIC_INFO["golden_cross_recent"]["help"],
    )
    hide_no_data = st.checkbox(
        "Ocultar empresas sin datos descargados", value=True,
        help="Oculta empresas que todavía no se han actualizado desde ⚙️ Configuración.",
    )

uni = screener.get_universe(limit=None)
with st.spinner(f"Cargando {len(uni)} empresas del universo..."):
    load_bar = st.progress(0.0)

    def _load_progress(done, total):
        load_bar.progress(done / total if total else 1.0)

    df = screener.build_screener_table(uni, weights=weights, progress_cb=_load_progress)
    load_bar.empty()

if df.empty:
    st.info("Todavía no hay datos. Ve a ⚙️ Configuración y pulsa 'Actualizar datos'.")
    st.stop()

filtered = df.copy()
if search_query.strip():
    q = search_query.strip().lower()
    name_match = filtered["name"].fillna("").str.lower().str.contains(q, regex=False)
    symbol_match = filtered.index.to_series().str.lower().str.contains(q, regex=False)
    filtered = filtered[name_match | symbol_match]
if hide_no_data:
    filtered = filtered[filtered["price"].notna() | filtered["pe"].notna()]
if min_market_cap_b > 0:
    filtered = filtered[filtered["market_cap"].fillna(0) >= min_market_cap_b * 1e9]
if only_golden_cross:
    filtered = filtered[filtered["golden_cross_recent"] == True]  # noqa: E712

if "sector" in filtered.columns:
    sectors = sorted([s for s in filtered["sector"].dropna().unique()])
    with st.sidebar:
        selected_sectors = st.multiselect(
            "Sector", sectors, default=[], format_func=translate_sector,
            help="Sector GICS de la empresa (nombres traducidos al español).",
        )
    if selected_sectors:
        filtered = filtered[filtered["sector"].isin(selected_sectors)]

st.caption(f"{len(filtered)} empresas (de {len(df)} en el universo analizado)")
st.caption("Cobertura = métricas puntuables disponibles / 13. El score compuesto requiere al menos el 50 % y datos en Value, Quality y Momentum.")

# --- Construcción de la tabla a mostrar: valores formateados + color por percentil ---
present_keys = [k for k in DISPLAY_KEYS if k in filtered.columns]
color_basis = build_color_basis(filtered, present_keys)

table = filtered[present_keys].copy()
if "sector" in table.columns:
    table["sector"] = table["sector"].map(translate_sector)
if "market_cap" in table.columns:
    table["market_cap"] = table["market_cap"] / 1e9
for col in present_keys:
    if col in FRACTION_COLUMNS:
        table[col] = table[col] * 100
    if col not in ("name", "sector"):
        table[col] = table[col].round(2)

label_map = {k: METRIC_INFO.get(k, {}).get("label", k.replace("_", " ").capitalize()) for k in present_keys}
table.rename(columns=label_map, inplace=True)
color_basis.rename(columns=label_map, inplace=True)
color_basis = color_basis.reindex(index=table.index, columns=table.columns)


def _apply_colors(_data):
    return color_basis.map(gradient_style)


styled = table.style.apply(_apply_colors, axis=None)

column_config = {}
for key in present_keys:
    label = label_map[key]
    help_text = METRIC_INFO.get(key, {}).get("help", "Cobertura de las métricas utilizadas en el score.")
    if key in ("name", "sector"):
        column_config[label] = st.column_config.TextColumn(label, help=help_text)
    else:
        column_config[label] = st.column_config.NumberColumn(label, help=help_text, format="%.2f")

st.dataframe(styled, width="stretch", height=500, column_config=column_config)

st.subheader("Seguimiento de rankings")
st.caption(
    "Guarda una foto del ranking de hoy (con los pesos actuales de ⚙️ Configuración) para poder revisar "
    "más adelante si esas candidatas batieron al SPY. Si cambias los pesos y guardas otro, ponle un "
    "nombre distinto — así podrás comparar 'con estos pesos' vs 'con estos otros' cuando los revises."
)
c1, c2 = st.columns([1, 2])
top_n = c1.number_input("Número de candidatas", min_value=1, max_value=50, value=10)
snapshot_name = c2.text_input(
    "Nombre de este ranking (opcional)", placeholder=f"Ranking {date.today().isoformat()}",
    help="Útil sobre todo si vas a probar varias configuraciones de pesos — te ayuda a saber luego con "
         "qué pesos se generó cada ranking guardado.",
)
if st.button("Guardar ranking de hoy"):
    snapshot_id = evaluation.save_snapshot(df, date.today().isoformat(), top_n=int(top_n),
                                           name=snapshot_name or None)
    if snapshot_id:
        st.success(f"Ranking #{snapshot_id} guardado. Sus resultados se podrán revisar a 6 y 12 meses.")
        st.rerun()
    else:
        st.warning("No hay candidatas con cobertura suficiente.")
snapshots = evaluation.list_snapshots()
if not snapshots.empty:
    labels = {int(row["id"]): f"{row['name']} · {row['as_of_date']} (#{row['id']})"
              for _, row in snapshots.iterrows()}
    selected_id = st.selectbox(
        "Ranking guardado", snapshots["id"].tolist(), format_func=lambda i: labels[i],
        help="Al cambiar esta selección se cargan las candidatas y la evaluación de ESE ranking concreto "
             "— cada uno guardó su propia fecha y sus propias empresas en el momento en que se creó.",
    )
    selected_row = snapshots[snapshots["id"] == selected_id].iloc[0]
    created_display = selected_row["created_at"].replace("T", " a las ")
    st.caption(f"Fecha objetivo: {selected_row['as_of_date']} · guardado el {created_display} (hora española) "
              f"· {selected_row['candidates']} candidatas")
    with st.form(f"rename_snapshot_{selected_id}"):
        new_name = st.text_input("Cambiar nombre de este ranking", value=selected_row["name"])
        if st.form_submit_button("Guardar nombre"):
            try:
                evaluation.rename_snapshot(int(selected_id), new_name)
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
    st.markdown(f"#### Progreso desde {selected_row['as_of_date']} hasta hoy")
    progress = evaluation.snapshot_progress(selected_id)
    if progress and progress.get("stale"):
        if progress["data_as_of"]:
            st.info(
                f"ℹ️ Los precios en caché solo llegan hasta el **{progress['data_as_of']}** — la misma fecha "
                "(o anterior) en que se guardó este ranking, así que todavía no hay ningún día nuevo que "
                "comparar (por eso el retorno sale en 0,0%, no es que no se haya movido nada). Actualiza los "
                "datos en ⚙️ Configuración y vuelve a mirarlo más tarde.",
            )
        else:
            st.info("ℹ️ Todavía no hay ningún precio cacheado para estas empresas. Actualiza los datos en ⚙️ Configuración.")
    if progress and progress["portfolio_return"] is not None:
        pc1, pc2, pc3 = st.columns(3)
        pc1.metric(
            "Cesta guardada", f"{progress['portfolio_return']:+.1%}",
            help="Media del retorno de cada candidata guardada desde la fecha del snapshot hasta hoy — "
                 "todas pesan igual (1/N), un ranking guardado no lleva pesos distintos por empresa.",
        )
        if progress["benchmark_return"] is not None:
            pc2.metric("SPY (mismo periodo)", f"{progress['benchmark_return']:+.1%}",
                      help="Qué habría rentado el SPY entre la misma fecha guardada y hoy.")
            pc3.metric("Diferencia", f"{progress['excess_return']:+.1%}",
                      help="Cesta menos SPY — positivo significa que la cesta bate al índice hasta ahora.")
        else:
            pc2.metric("SPY (mismo periodo)", "—")
        if progress["available"] < progress["requested"]:
            st.caption(
                f"⚠️ Cobertura {progress['available']}/{progress['requested']} — sin precio hasta hoy para: "
                + ", ".join(progress["missing"]) + " (no cuentan como 0%, simplemente se excluyen de la media)."
            )

        curve = evaluation.snapshot_price_curve(selected_id)
        if not curve.empty:
            st.line_chart(curve, y_label="Valor (100 = fecha guardada)")

        st.caption(f"Detalle por empresa — exactamente las {progress['requested']} candidatas guardadas, ninguna más:")
        detail = progress["detail"].copy()
        detail["return"] = detail["return"] * 100
        detail = detail.rename(columns={
            "symbol": "Ticker", "price_start": f"Precio {progress['as_of_date']}",
            "price_now": "Precio hoy", "return": "Retorno %",
        })
        st.dataframe(
            detail, hide_index=True, width="stretch",
            column_config={
                "Retorno %": st.column_config.NumberColumn("Retorno %", format="%.1f%%"),
                f"Precio {progress['as_of_date']}": st.column_config.NumberColumn(format="%.2f"),
                "Precio hoy": st.column_config.NumberColumn(format="%.2f"),
            },
        )
    else:
        st.info("Sin precios suficientes todavía para calcular el progreso de este ranking.")

    with st.expander("Ver también a plazo fijo (6 y 12 meses desde que se guardó)"):
        st.caption("Referencia adicional con un punto de corte fijo, útil para comparar entre rankings de forma homogénea.")
        for months in (6, 12):
            outcome = evaluation.evaluate(evaluation.snapshot_symbols(selected_id), selected_row["as_of_date"], months)
            if outcome["status"] == "pending":
                st.write(f"{months} meses: pendiente hasta {outcome['end_date']}")
            else:
                pf = f"{outcome['portfolio_return']:+.1%}" if outcome["portfolio_return"] is not None else "—"
                spy = f"{outcome['benchmark_return']:+.1%}" if outcome["benchmark_return"] is not None else "—"
                st.write(f"{months} meses: candidatas {pf} · SPY {spy} · cobertura {outcome['available']}/{outcome['requested']}")
                if outcome["status"] == "incomplete":
                    st.caption("Resultado parcial: faltan precios para " + ", ".join(outcome["missing"]))

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
