import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import pandas as pd
import streamlit as st

from gabi import config, data_health, scoring, screener
from gabi.ui_helpers import METRIC_INFO, translate_sector

st.title("🩺 Salud de los datos")
st.caption(
    "Cobertura y frescura de cada fuente para el universo descargado, y de dónde procede cada pieza "
    "del score de una empresa concreta. Esta página no descarga nada -- solo lee lo que ya hay en caché."
)


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


uni = screener.get_universe(limit=None)
symbols = uni["symbol"].tolist()

st.subheader("Resumen de universo")
st.caption(f"{len(symbols)} empresas en el universo actual (S&P 500).")
summary = data_health.universe_summary(symbols)

rows = [
    {
        "Fuente": s["label"],
        "Cobertura": f"{s['coverage']:.0%} ({s['have']}/{s['total']})" if "have" in s else f"{s['coverage']:.0%}",
        "Frescura": f"{_status_icon(s['fresh'])} {s['fresh']:.0%}",
        "Umbral de frescura": _fmt_age(s["threshold_hours"]),
        "Dato más antiguo": _fmt_age(s.get("oldest_hours")),
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
        f"De las empresas con SEC EDGAR, {edgar_summary['with_facts_pct']:.0%} tienen además el histórico "
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
prov = data_health.symbol_provenance(symbol)


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
        weights = config.load_weights()
        load_bar = st.progress(0.0)
        df = screener.build_screener_table(
            uni, weights=weights,
            progress_cb=lambda done, total: load_bar.progress(done / total if total else 1.0),
        )
        load_bar.empty()
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
