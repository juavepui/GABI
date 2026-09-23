import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import pandas as pd
import streamlit as st

from gabi import config, data_quality, historical_archive, identity, scoring, screener, storage
from gabi.ui_helpers import METRIC_INFO, translate_sector

st.title("🩺 Calidad de los datos")
st.caption(
    "Cobertura, frescura y procedencia de cada fuente para el universo descargado -- no solo qué score "
    "produce un símbolo, sino con qué calidad de dato se calculó. Esta página no descarga nada -- solo "
    "lee lo que ya hay en caché."
)

st.warning(
    "\n\n".join(f"**Limitación estructural conocida:** {msg}" for msg in data_quality.STRUCTURAL_LIMITATIONS),
    icon="⚠️",
)

with st.expander("Archivo histórico anterior a 2016"):
    st.caption(
        "Fuentes históricas descargadas para investigación. La composición de los primeros años puede ser incompleta. "
        "Los precios archivados conservan los ajustes de su fuente y requieren validar la identidad de cada empresa "
        "antes de incorporarlos a un backtest. Los fundamentales estructurados de SEC empiezan en 2009. "
        "Los informes nuevos se conservan por CIK; su asociación con tickers antiguos queda pendiente de acreditar."
    )
    if st.button("Consultar cobertura del archivo"):
        st.session_state["historical_archive_summary"] = historical_archive.source_summary()
    archive_summary = st.session_state.get("historical_archive_summary", [])
    if archive_summary:
        st.dataframe(pd.DataFrame(archive_summary), hide_index=True, width="stretch")
        membership_sources = [r["Fuente"] for r in archive_summary if r["Datos"] == "Composición"]
        if membership_sources:
            archive_date = st.date_input("Fecha de composición archivada", value=date(1996, 1, 2),
                                         min_value=date(1996, 1, 2), max_value=date(2015, 12, 31))
            if st.button("Ver miembros del índice en el archivo"):
                snapshot = historical_archive.get_membership(membership_sources[0], archive_date.isoformat())
                st.write(f"{len(snapshot['symbols'])} valores en la composición registrada el {snapshot['source_date']}.")
                st.dataframe(pd.DataFrame({"Símbolo": snapshot["symbols"]}), hide_index=True)
        price_sources = [r["Fuente"] for r in archive_summary if r["Datos"] == "Precios"]
        if price_sources:
            archive_symbol = st.text_input("Símbolo para consultar precios archivados", value="ATVI").strip().upper()
            if st.button("Ver precios del archivo"):
                archived = historical_archive.get_prices(price_sources[0], archive_symbol, "1996-01-02", "2016-01-01")
                if archived.empty:
                    st.info("El archivo no tiene precios de ese símbolo en este periodo.")
                else:
                    st.caption("Cierre original y cierre ajustado según la fuente; la fecha final mostrada es 2015.")
                    st.dataframe(archived[["close", "adj_close", "volume"]].rename(
                        columns={"close": "Cierre", "adj_close": "Cierre ajustado", "volume": "Volumen"}), width="stretch")


def _fmt_age(hours):
    if hours is None:
        return "—"
    if hours < 48:
        return f"{hours:.0f} h"
    return f"{hours / 24:.0f} días"


def _status_icon(fraction: float) -> str:
    if fraction >= 0.9:
        return "🟢"
    if fraction >= 0.5:
        return "🟡"
    return "🔴"


if not config.SP500_CACHE.exists():
    st.warning("Universo ausente en caché. Actualiza los datos en Configuración para iniciar el diagnóstico.")
    st.stop()
uni = pd.read_csv(config.SP500_CACHE)
if uni.empty:
    st.warning("El universo local está vacío.")
    st.stop()
symbols = uni["symbol"].tolist()


def _scored_universe():
    """Cachea en session_state -- lo usan tanto la cobertura por bloque
    (todo el universo) como el score de una empresa concreta, y construirlo
    (500 empresas) es lo único caro de esta página."""
    weights = config.load_weights()
    fingerprint = data_quality.compute_data_fingerprint(symbols, inputs={"weights": weights})
    if st.session_state.get("dq_fingerprint") != fingerprint:
        load_bar = st.progress(0.0)
        st.session_state["dq_scored_universe"] = screener.build_screener_table(
            uni, weights=weights,
            progress_cb=lambda done, total: load_bar.progress(done / total if total else 1.0),
        )
        load_bar.empty()
        st.session_state["dq_fingerprint"] = fingerprint
    return st.session_state["dq_scored_universe"]

st.subheader("Resumen de universo")
st.caption(f"{len(symbols)} empresas en el universo actual (S&P 500).")
summary = data_quality.universe_summary(symbols)
st.caption("Estado global: degradado por limitaciones estructurales conocidas. La frescura de una fuente no certifica calidad point-in-time.")

rows = [
    {
        "Fuente": s["label"],
        "Cobertura": f"{s['coverage']:.0%} ({s['have']}/{s['total']})" if "have" in s else f"{s['coverage']:.0%}",
        "Frescura": f"{_status_icon(s['fresh'])} {s['fresh']:.0%}",
        "Umbral de frescura": _fmt_age(s["threshold_hours"]),
        "Dato más antiguo": s.get("oldest_date") or _fmt_age(s.get("oldest_hours")),
    }
    for s in summary["sources"].values()
]
st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
st.caption(
    "🟢 ≥90% dentro del umbral de frescura de esa fuente · 🟡 ≥50% · 🔴 por debajo. \"Cobertura\" es si "
    "existe algún dato cacheado; \"frescura\" es si ese dato es reciente según el umbral de cada fuente "
    "(24h fundamentales/insider, 7 días SEC EDGAR, 5 días naturales precios)."
)

edgar_summary = summary["sources"].get("edgar", {})
if "with_facts_pct" in edgar_summary:
    st.caption(
        f"Del universo completo, {edgar_summary['with_facts_pct']:.0%} tienen además el histórico "
        "XBRL completo (`edgar_facts`) que hace falta para reconstruir rankings pasados en 🕰️ Ranking "
        "histórico -- tener solo `edgar_metrics` (el resumen actual) no basta para eso."
    )

c1, c2 = st.columns(2)
if summary["cik"]:
    c1.metric(
        "CIK resueltos (SEC)", f"{summary['cik']['pct']:.0%}",
        help=f"{summary['cik']['resolved']}/{summary['cik']['total']} símbolos con CIK identificado en la "
             "SEC -- sin esto, SEC EDGAR no puede aportar nada para esa empresa (ni en vivo ni en un "
             "backtest). El mapeo de la SEC solo cubre registrantes ACTIVOS hoy, así que empresas ya "
             "deslistadas quedan sin resolver salvo que ya se resolvieran antes.",
    )
else:
    c1.caption("Mapeo de CIK de la SEC aún no descargado (se hace al actualizar datos en ⚙️ Configuración).")
if summary["macro"]:
    c2.metric(
        "Series macro descargadas (FRED)", summary["macro"]["n_series"],
        help=f"Serie más antigua sin refrescar: {_fmt_age(summary['macro']['oldest_hours'])} "
             f"(umbral {summary['macro']['threshold_hours']}h).",
    )
else:
    c2.caption("Sin datos macro descargados todavía -- ver 🌐 Panel Macro.")

with st.expander("FRED: Última observación disponible por serie"):
    st.dataframe(pd.DataFrame([
        {"Serie": key, "Última observación": value or "ausente"}
        for key, value in summary["sources"]["fred"]["latest_dates"].items()
    ]), hide_index=True)

recent_errors = data_quality.recent_errors_summary()
if recent_errors.empty:
    st.caption("✅ Sin fallos de actualización registrados en los últimos 7 días.")
else:
    with st.expander(f"🔴 {len(recent_errors)} fallo(s) de actualización en los últimos 7 días"):
        st.dataframe(recent_errors, hide_index=True, width="stretch")
        st.caption(
            "Fuente · símbolo · motivo · cuándo. Se guardan al actualizar datos desde ⚙️ Configuración / "
            "🌐 Panel Macro -- antes se mostraban una vez tras el refresco y se perdían."
        )

with st.expander("📐 Cobertura por bloque del score (todo el universo)"):
    st.caption(
        "Qué % del universo tiene datos COMPLETOS para cada bloque del score (Value/Quality/Momentum/"
        "Risk), no solo si la fuente está fresca -- calcula el ranking completo (sin red), puede tardar "
        "unos segundos."
    )
    if st.button("Calcular", key="block_coverage_button"):
        block_coverage = data_quality.score_block_coverage(_scored_universe())
        block_rows = [
            {"Bloque": block.capitalize(), "Nº métricas": info["n_metrics"],
             "Completo (todas)": f"{info['complete']:.0%}", "Al menos una": f"{info['any']:.0%}",
             "Ninguna": f"{info['none']:.0%}"}
            for block, info in block_coverage.items()
        ]
        st.dataframe(pd.DataFrame(block_rows), hide_index=True, width="stretch")
        st.caption(
            "\"Completo\" = tiene dato en TODAS las métricas oficiales de ese bloque (`scoring.SCORE_METRICS`) "
            "-- una empresa con solo 1 de 4 métricas de Quality no cuenta aquí como completa, aunque "
            "`quality_score` le dé un valor (ver `scoring.compute_confidence` para ese caso por empresa)."
        )

st.divider()
st.subheader("Procedencia de una empresa")
st.caption("Qué fuente y qué fecha respalda cada dato detrás del resultado de una empresa concreta.")


def _label(sym):
    name = uni.loc[uni["symbol"] == sym, "name"]
    return f"{sym} — {name.iloc[0]}" if not name.empty and pd.notna(name.iloc[0]) else sym


symbol = st.selectbox(
    "Empresa", symbols,
    index=symbols.index(st.session_state["selected_symbol"]) if st.session_state.get("selected_symbol") in symbols else 0,
    format_func=_label,
)
reference_date = st.date_input("Fecha de referencia del sector point-in-time")
prov = data_quality.symbol_provenance(symbol, as_of=reference_date.isoformat())
resolution = identity.resolve(symbol, reference_date.isoformat())
st.write(f"Identidad a {reference_date}: **{resolution['status']}** · entidad: {resolution['entity_id'] or 'sin acreditar'}")
if resolution["candidates"]:
    st.caption("Entidades candidatas: " + ", ".join(resolution["candidates"]))
with st.expander("Diagnóstico de identidad del universo"):
    if st.button("Comprobar identidades por fecha"):
        identities = identity.diagnostics(symbols, reference_date.isoformat())
        st.dataframe(identities, hide_index=True)
        st.caption(f"{identities['cik'].isna().sum()} símbolos sin CIK acreditado para esta fecha.")
    with storage.get_connection() as conn:
        identity.ensure_schema(conn)
        candidates = pd.read_sql_query("SELECT * FROM entity_candidates WHERE symbol=?", conn,
                                       params=(identity.normalize_symbol(symbol),))
    if not candidates.empty:
        st.caption("Coincidencias por nombre pendientes de evidencia temporal; no se usan para el score.")
        st.dataframe(candidates, hide_index=True)
st.caption(f"CIK: {prov['cik'] or 'no resuelto'}")
if not recent_errors.empty:
    symbol_errors = recent_errors[recent_errors["symbol"] == symbol]
    if not symbol_errors.empty:
        st.warning(f"{len(symbol_errors)} errores recientes de actualización para {symbol}.")
        st.dataframe(symbol_errors, hide_index=True)


def _source_row(name, info, extra=""):
    age = info.get("age_hours")
    threshold = info.get("threshold_hours")
    if age is None:
        status = "⚪ sin descargar"
    elif age <= threshold:
        status = "🟢 fresco"
    else:
        status = f"🔴 desactualizado ({_fmt_age(age)} > {_fmt_age(threshold)})"
    return {"Fuente": name, "Última descarga": _fmt_age(age) + " atrás" if age is not None else "—",
            "Estado": status, "Detalle": extra}


detail_rows = [
    _source_row(
        "Precios (Yahoo)", prov["prices"],
        extra=(f"{prov['prices']['adjusted_sessions']} sesiones, última: {prov['prices']['latest_date']}"
               if prov["prices"]["latest_date"] else "sin precios cacheados"),
    ),
    _source_row("Fundamentales (Yahoo)", prov["fundamentals"]),
    _source_row(
        "SEC EDGAR", prov["edgar"],
        extra=(f"10-K: {prov['edgar']['latest_10k_date'] or '—'} · 10-Q: {prov['edgar']['latest_10q_date'] or '—'}"
               f" · histórico XBRL: {'sí' if prov['edgar']['has_facts'] else 'no'}"),
    ),
    _source_row("Insider (Form 4)", prov["insider"]),
]
em = prov["entity_master"]
if em["status"] == "missing":
    em_status, em_detail = "⚪ sin foto nunca", "no hay sector point-in-time disponible para esta empresa"
elif em["is_approximate"]:
    em_status, em_detail = "🟡 aproximado", f"sector actual ({em['sector'] or '—'}), no el real de una fecha pasada"
else:
    em_status, em_detail = "🟢 point-in-time real", f"sector: {em['sector'] or '—'}"
detail_rows.append({
    "Fuente": "Entity Master (sector)",
    "Última descarga": em["effective_date"] or "—",
    "Estado": em_status, "Detalle": em_detail,
})
st.dataframe(pd.DataFrame(detail_rows), hide_index=True, width="stretch")
st.caption(
    "\"Última descarga\" es cuándo GABI trajo el dato, no la fecha del propio informe -- una descarga de "
    "ayer puede seguir respaldada por un 10-K de hace más de un año si la empresa no ha presentado nada "
    "nuevo desde entonces (columna Detalle)."
)

with st.expander("📊 Ver también su score y confidence actuales"):
    st.caption(
        "Calcula el ranking completo del universo (solo con datos ya cacheados, sin red) para poder "
        "mostrar el score de esta empresa en su contexto -- puede tardar unos segundos."
    )
    if st.button("Calcular"):
        df = _scored_universe()
        if symbol not in df.index:
            st.info("Esta empresa no tiene fila en el ranking (sin datos suficientes).")
        else:
            row = df.loc[symbol]
            sector_es = translate_sector(row.get("sector")) or "Sector desconocido"
            st.write(f"**{row.get('name') or symbol}** ({symbol}) — {sector_es}")
            m1, m2, m3, m4, m5, m6 = st.columns(6)
            for col, key, label in (
                (m1, "composite_score", "Composite"), (m2, "value_score", "Value"),
                (m3, "quality_score", "Quality"), (m4, "momentum_score", "Momentum"),
                (m5, "risk_score", "Risk"), (m6, "confidence", "Confidence"),
            ):
                value = row.get(key)
                col.metric(label, f"{value:.0f}" if pd.notna(value) else "—", help=METRIC_INFO[key]["help"])
            breakdown = scoring.explain_row(df, symbol)
            if not breakdown.empty:
                st.dataframe(breakdown, hide_index=True, width="stretch")
