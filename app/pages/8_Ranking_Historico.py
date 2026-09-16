import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import pandas as pd
import streamlit as st

from gabi import config, data_fetch, edgar, screener_asof, universe
from gabi.ui_helpers import FRACTION_COLUMNS, METRIC_INFO, build_color_basis, gradient_style, translate_sector

st.title("🕰️ Ranking histórico")
st.warning(
    "⚠️ **Experimental.** Reconstruye lo que el screener habría mostrado en una fecha pasada, usando "
    "solo datos que ya se conocían ese día (sin mirar al futuro). No sustituye a un backtest real — "
    "sirve para explorar, no para sacar conclusiones estadísticas de una sola fecha.",
    icon="⚠️",
)

with st.expander("ℹ️ Cómo funciona y sus límites (léelo antes de usarlo)"):
    st.markdown(
        """
- **Universo**: se reconstruye qué empresas formaban realmente el S&P 500 ese día (evita el sesgo de
  supervivencia de usar la lista actual) con datos de la comunidad
  ([`hanshof/sp500_constituents`](https://github.com/hanshof/sp500_constituents), sin garantías,
  cobertura hasta 2025-08-23 — para fechas más recientes se usa el universo actual como aproximación).
- **Fundamentales y múltiplos** (ROIC, márgenes, deuda neta/EBITDA, PER, P/VC, P/Ventas, EV/EBITDA):
  100% desde SEC EDGAR con la fecha real de presentación de cada dato — nunca desde Yahoo Finance, que
  no guarda histórico.
- **Precio y capitalización**: el histórico de precios normal solo cubre ~2 años. Para fechas más
  antiguas hace falta pedir el histórico completo (botón de abajo) — puede no estar disponible para
  empresas muy antiguas o ya deslistadas.
- ⚠️ **Los tickers se reciclan.** Cuando una empresa desaparece, la bolsa puede reasignar su símbolo a
  otra empresa completamente distinta años después (comprobado: "APC" era Anadarko Petroleum en 2019 y
  hoy en la SEC es "ARKO Petroleum Corp"). Por eso cada fila muestra el **nombre registrado en la SEC**
  junto al ticker — si no coincide con lo que esperabas, no te fíes de esos datos.
        """
    )

col1, col2 = st.columns([1, 2])
with col1:
    as_of = st.date_input(
        "Fecha a reconstruir", value=date(2019, 6, 3),
        min_value=date(1996, 1, 2), max_value=date.today() - timedelta(days=1),
        help="El screener se reconstruye tal y como se habría visto al cierre de este día.",
    )
with col2:
    size_choice = st.radio(
        "Tamaño del universo", ["Prueba rápida (15 empresas)", "Medio (50 empresas)", "Completo"],
        index=0, horizontal=True,
        help="El universo completo de una fecha antigua puede tener ~500 símbolos, muchos ya "
             "deslistados — prepararlos todos tarda bastante.",
    )
limit_map = {"Prueba rápida (15 empresas)": 15, "Medio (50 empresas)": 50, "Completo": None}
limit = limit_map[size_choice]
as_of_str = as_of.isoformat()

universe_info = universe.get_sp500_constituents_asof(as_of_str)
symbols = universe_info["symbols"]
if limit:
    symbols = symbols[:limit]

if universe_info["is_exact"]:
    st.caption(f"✅ {universe_info['note']}")
else:
    st.caption(f"⚠️ {universe_info['note']}")

st.caption(f"{len(symbols)} empresas en el universo a preparar/mostrar para esta fecha.")

if st.button("🔄 Preparar datos que falten para esta fecha", type="primary"):
    edgar_bar = st.progress(0.0, text="SEC EDGAR: preparando...")

    def edgar_progress_cb(done, total, sym):
        edgar_bar.progress(min(done / total, 1.0) if total else 1.0, text=f"SEC EDGAR: {done}/{total} ({sym})")

    with st.spinner("Descargando fundamentales SEC EDGAR..."):
        edgar_result = edgar.ensure_edgar_data(symbols, progress_cb=edgar_progress_cb)
    edgar_bar.progress(1.0, text="SEC EDGAR: completado")

    price_bar = st.progress(0.0, text="Precios: comprobando cobertura...")

    def price_progress_cb(done, total, sym):
        price_bar.progress(min(done / total, 1.0) if total else 1.0, text=f"Precios (histórico completo): {done}/{total}")

    with st.spinner("Ampliando histórico de precios donde haga falta..."):
        price_result = data_fetch.ensure_price_history_asof(symbols, as_of_str, progress_cb=price_progress_cb)
    price_bar.progress(1.0, text="Precios: completado")

    st.success(
        f"SEC EDGAR actualizado: {edgar_result['edgar_refreshed']} · fallos: {len(edgar_result['failed'])} · "
        f"Precios ampliados: {price_result['deep_fetched']} (ya cubrían la fecha: {price_result['already_covered']}) "
        f"· fallos de precio: {len(price_result['failed'])}"
    )
    all_failed = {}
    for sym, reason in edgar_result["failed"].items():
        all_failed.setdefault(sym, {})["edgar"] = reason
    for sym, reason in price_result["failed"].items():
        all_failed.setdefault(sym, {})["precio"] = reason
    if all_failed:
        with st.expander(f"Ver los {len(all_failed)} símbolos con algún fallo"):
            rows = [{"symbol": s, "etapa": k, "motivo": v} for s, stages in all_failed.items() for k, v in stages.items()]
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

st.divider()

result = screener_asof.build_ranking_as_of(as_of_str, symbols=symbols)
df = result["table"]

if df.empty:
    st.info("Sin datos todavía para este universo. Pulsa 'Preparar datos' arriba.")
    st.stop()

has_price = df["market_cap"].notna()
n_with_price = int(has_price.sum())
n_with_fundamentals = int(df["roic"].notna().sum())
st.caption(
    f"{len(df)} empresas en la tabla · {n_with_fundamentals} con fundamentales reconstruidos · "
    f"{n_with_price} con precio/capitalización de esa fecha (requiere histórico de precios profundo)."
)

hide_no_data = st.checkbox("Ocultar empresas sin ningún dato reconstruido", value=True)
filtered = df[df["roic"].notna() | df["market_cap"].notna()] if hide_no_data else df

DISPLAY_KEYS = [
    "resolved_title", "sector", "market_cap", "price", "pe", "pb", "roic",
    "gross_margin", "operating_margin", "debt_to_equity", "net_debt_to_ebitda",
    "revenue_growth_yoy", "revenue_cagr_3y", "fcf_cagr_3y", "fundamentals_period_end",
    "value_score", "quality_score", "momentum_score", "risk_score", "composite_score",
]

table_source = filtered.copy()
table_source["resolved_title"] = [edgar.get_resolved_title(s) or filtered.loc[s, "name"] or s for s in filtered.index]

present_keys = [k for k in DISPLAY_KEYS if k in table_source.columns]
color_basis = build_color_basis(table_source, [k for k in present_keys if k != "resolved_title"])


def _format_cell(col, value):
    if col in ("resolved_title", "sector"):
        if col == "sector":
            return translate_sector(value) or "—"
        return value or "—"
    from gabi.ui_helpers import format_metric_value
    return format_metric_value(col, value)


table = pd.DataFrame(
    {col: table_source[col].map(lambda v, c=col: _format_cell(c, v)) for col in present_keys},
    index=table_source.index,
)
label_map = {k: METRIC_INFO.get(k, {}).get("label", k) for k in present_keys}
label_map["resolved_title"] = "Empresa (nombre SEC)"
table.rename(columns=label_map, inplace=True)
color_basis.rename(columns=label_map, inplace=True)
color_basis = color_basis.reindex(index=table.index, columns=table.columns)


def _apply_colors(_data):
    return color_basis.map(gradient_style)


styled = table.style.apply(_apply_colors, axis=None)
st.dataframe(styled, width="stretch", height=500)
st.caption(
    "🟩 mejor · 🟨 medio · 🟥 peor, comparado con el resto de empresas de su sector (sector actual — no "
    "hay fuente gratuita de sector histórico). Las columnas sin color no se usan para puntuar."
)
