import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import pandas as pd
import streamlit as st

from gabi import evaluation, signal_monitor

st.title("📡 Signal Monitor")
st.caption(
    "Compara el ranking en vivo con el último snapshot guardado en 📊 Screener y detecta qué cambió "
    "-- entradas/salidas del Top-N, cambios de rank/score/confidence por encima de un umbral, y cambios "
    "de sector. Solo lee datos ya cacheados, sin red."
)
st.warning(
    "⚠️ **Ningún evento de esta página es una recomendación de compra/venta.** Es un diagnóstico de qué "
    "cambió desde la última foto guardada -- la decisión sigue siendo tuya (o de 🧭 Decisiones de cartera).",
    icon="⚠️",
)

SEVERITY_ICON = {"MATERIAL": "🔴", "WATCH": "🟡", "INFO": "⚪"}
EVENT_LABEL = {
    "top_n_entry": "Entra en el Top-N", "top_n_exit": "Sale del Top-N",
    "score_change": "Cambio de Composite Score", "rank_change": "Cambio de rank",
    "confidence_drop": "Caída de Confidence", "sector_change": "Cambio de sector",
    "eligibility_change": "Deja de tener score calculable",
}


def _format_events(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    out["Evento"] = out["event_type"].map(lambda t: EVENT_LABEL.get(t, t))
    out["Severidad"] = out["severity"].map(lambda s: f"{SEVERITY_ICON.get(s, '')} {s}")
    out["Antes"] = out["previous_value"].map(lambda v: "—" if v is None else v)
    out["Ahora"] = out["new_value"].map(lambda v: "—" if v is None else v)
    return out[["detected_at", "symbol", "Evento", "Severidad", "Antes", "Ahora", "cause"]].rename(columns={
        "detected_at": "Detectado", "symbol": "Símbolo", "cause": "Motivo",
    })


snapshots = evaluation.list_snapshots()
if snapshots.empty:
    st.info("Todavía no hay ningún snapshot guardado. Guarda uno desde 📊 Screener → "
            "\"Seguimiento de rankings\" antes de poder comparar.")
    st.stop()

st.subheader("Comparar con un snapshot")
labels = {int(row["id"]): f"{row['name']} · {row['created_at'][:16]} ({row['candidates']} candidatas)"
          for _, row in snapshots.iterrows()}
selected_snapshot = st.selectbox(
    "Snapshot de referencia", snapshots["id"].tolist(), format_func=lambda i: labels[i],
    help="El ranking en vivo se compara contra este snapshot -- por defecto, el más reciente guardado.",
)

with st.expander("⚙️ Umbrales (evitan avisos por ruido diario)"):
    c1, c2, c3 = st.columns(3)
    rank_threshold = c1.number_input(
        "Cambio de rank (posiciones)", min_value=1, value=signal_monitor.DEFAULT_THRESHOLDS["rank_change"],
        help="Un símbolo que se mueve menos de esto en el ranking no genera aviso.")
    score_threshold = c2.number_input(
        "Cambio de Composite Score (puntos)", min_value=0.1,
        value=signal_monitor.DEFAULT_THRESHOLDS["score_change"], step=0.5,
        help="Escala 0-100. Genera un evento MATERIAL si se supera.")
    confidence_threshold = c3.number_input(
        "Caída de Confidence (puntos)", min_value=0.1,
        value=signal_monitor.DEFAULT_THRESHOLDS["confidence_drop"], step=0.5,
        help="Escala 0-100. Solo caídas -- una subida de confidence nunca genera aviso.")

if st.button("🔍 Comparar con el ranking en vivo", type="primary"):
    with st.spinner("Calculando el ranking en vivo y comparando..."):
        result = signal_monitor.run_comparison(
            snapshot_id=int(selected_snapshot),
            thresholds={"rank_change": int(rank_threshold), "score_change": float(score_threshold),
                       "confidence_drop": float(confidence_threshold)},
        )
    if result["reason"]:
        st.error(result["reason"])
    elif not result["events"]:
        st.success("Sin cambios relevantes desde el snapshot elegido -- nada por encima de los umbrales.")
    else:
        counts = pd.Series([e["severity"] for e in result["events"]]).value_counts()
        m1, m2, m3 = st.columns(3)
        m1.metric("🔴 MATERIAL", int(counts.get("MATERIAL", 0)))
        m2.metric("🟡 WATCH", int(counts.get("WATCH", 0)))
        m3.metric("⚪ INFO", int(counts.get("INFO", 0)))
        st.dataframe(_format_events(pd.DataFrame(result["events"]).assign(
            detected_at=result["compared_at"])), hide_index=True, width="stretch")
        st.caption("Los eventos ya han quedado guardados -- consúltalos más abajo en cualquier momento, "
                   "aunque cierres esta página. Repetir la comparación con el mismo snapshot no duplica eventos.")

st.divider()
st.subheader("Eventos recientes")
f1, f2 = st.columns([1, 2])
severity_filter = f1.selectbox("Severidad", ["(todas)"] + list(signal_monitor.SEVERITIES))
since_hours = f2.slider("Últimas N horas", min_value=1, max_value=24 * 30, value=24 * 7,
                        help="Por defecto, la última semana.")

events_df = signal_monitor.list_events(
    severity=None if severity_filter == "(todas)" else severity_filter, since_hours=since_hours)
if events_df.empty:
    st.caption("Sin eventos registrados en esta ventana.")
else:
    st.dataframe(_format_events(events_df.rename(columns={"detected_at": "detected_at"})),
                hide_index=True, width="stretch")

st.divider()
st.subheader("Futuro: notificaciones fuera de la app")
st.caption(
    "El motor de señales (`signal_monitor.compare_snapshots`) no conoce ningún proveedor de notificación: "
    "`signal_monitor.Notifier` es una interfaz -- `InAppNotifier` (la que usa esta página) es la única "
    "implementación hoy, pero un `EmailNotifier`/`TelegramNotifier` futuro implementaría el mismo "
    "`notify(event)` sin tocar la detección de eventos."
)
