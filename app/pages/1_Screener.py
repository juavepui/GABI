import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import streamlit as st

from gabi import config, screener
from gabi.ui_helpers import FRACTION_COLUMNS, METRIC_INFO, build_color_basis, gradient_style, translate_sector

st.set_page_config(page_title="Screener — GABI", page_icon="📊", layout="wide")
st.title("📊 Screener")
st.caption(
    "Los colores indican la posición de cada empresa **dentro de su sector** para esa métrica "
    "(comparar el PER de un banco con el de una tecnológica no tiene sentido): 🟩 mejor · 🟨 medio · "
    "🟥 peor. Pasa el ratón sobre el nombre de cada columna para ver qué significa."
)

# Columnas que se muestran en la tabla, en orden.
DISPLAY_KEYS = [
    "name", "sector", "market_cap", "pe", "roe", "roic", "revenue_growth_yoy",
    "price", "price_vs_sma50", "rsi14",
    "value_score", "quality_score", "momentum_score", "composite_score",
]

saved_weights = config.load_weights()

with st.sidebar:
    st.header("Pesos del score")
    st.caption(
        "💡 Si estás empezando, considera dar más peso a Value y Quality que a Momentum: "
        "los fundamentos importan más que los indicadores técnicos al principio."
    )
    w_value = st.slider("Value", 0, 100, int(saved_weights.get("value", 0.35) * 100), help=METRIC_INFO["value_score"]["help"])
    w_quality = st.slider("Quality", 0, 100, int(saved_weights.get("quality", 0.35) * 100), help=METRIC_INFO["quality_score"]["help"])
    w_momentum = st.slider("Momentum", 0, 100, int(saved_weights.get("momentum", 0.30) * 100), help=METRIC_INFO["momentum_score"]["help"])
    total_w = max(w_value + w_quality + w_momentum, 1)
    weights = {"value": w_value / total_w, "quality": w_quality / total_w, "momentum": w_momentum / total_w}

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
df = screener.build_screener_table(uni, weights=weights)

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

label_map = {k: METRIC_INFO[k]["label"] for k in present_keys}
table.rename(columns=label_map, inplace=True)
color_basis.rename(columns=label_map, inplace=True)
color_basis = color_basis.reindex(index=table.index, columns=table.columns)


def _apply_colors(_data):
    return color_basis.map(gradient_style)


styled = table.style.apply(_apply_colors, axis=None)

column_config = {}
for key in present_keys:
    label = METRIC_INFO[key]["label"]
    help_text = METRIC_INFO[key]["help"]
    if key in ("name", "sector"):
        column_config[label] = st.column_config.TextColumn(label, help=help_text)
    else:
        column_config[label] = st.column_config.NumberColumn(label, help=help_text, format="%.2f")

st.dataframe(styled, width="stretch", height=500, column_config=column_config)

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
