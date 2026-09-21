import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import streamlit as st

from gabi import config, macro

st.title("🌐 Panel macro")
st.caption(
    "Contexto para tus tesis del Diario de inversión — no se usa (todavía) en el score, porque saber "
    "qué factor funciona bajo qué régimen requiere el backtesting histórico que decidimos no construir "
    "aún sin datos point-in-time fiables."
)

api_key = config.load_fred_key()
if not api_key:
    st.warning(
        "Necesitas una API key gratuita de FRED para ver esto (alta inmediata, sin tarjeta, "
        "~2 minutos): [fred.stlouisfed.org/docs/api/api_key.html]"
        "(https://fred.stlouisfed.org/docs/api/api_key.html). Luego pégala en ⚙️ Configuración.",
        icon="🔑",
    )
    st.stop()

if st.button("🔄 Actualizar datos macro"):
    progress_bar = st.progress(0.0, text="Descargando series de FRED...")

    def progress_cb(done, total, sid):
        progress_bar.progress(min(done / total, 1.0) if total else 1.0, text=f"FRED: {done}/{total} ({sid})")

    result = macro.ensure_macro_data(force=True, progress_cb=progress_cb)
    progress_bar.progress(1.0, text="Completado")
    if result["failed"]:
        st.error(f"{len(result['failed'])} series fallaron: {result['failed']}")
    else:
        st.success(f"{result['refreshed']} series actualizadas.")
else:
    with st.spinner("Comprobando si hay series desactualizadas..."):
        macro.ensure_macro_data(force=False)  # descarga silenciosa si hace falta, sin barra de progreso

snapshot = macro.get_snapshot()
available = snapshot[snapshot["latest_value"].notna()]

if available.empty:
    st.info("Todavía no hay datos descargados. Pulsa '🔄 Actualizar datos macro'.")
    st.stop()

cols = st.columns(3)
for i, (_, row) in enumerate(available.iterrows()):
    col = cols[i % 3]
    delta = f"{row['change_3m']:+.2f} (3 meses)" if row["change_3m"] is not None else None
    col.metric(
        row["label"], f"{row['latest_value']:.2f} {row['unit']}", delta=delta, help=row["help"],
    )
    col.caption(f"Dato a {row['latest_date']}")

missing = snapshot[snapshot["latest_value"].isna()]
if not missing.empty:
    st.caption(f"Sin datos todavía: {', '.join(missing['label'])} — pulsa actualizar de nuevo.")

st.divider()
st.subheader("📅 Próximo evento macro conocido")
try:
    next_cpi = macro.fetch_next_release_date("CPIAUCSL", api_key)
except Exception:
    next_cpi = None
if next_cpi:
    days_until = (next_cpi - date.today()).days
    st.caption(
        f"🗓️ **Inflación (CPI)**: próxima publicación programada el {next_cpi.isoformat()} (en {days_until} "
        "días) — fecha confirmada por la fuente oficial (BLS, vía FRED), no una estimación de GABI."
    )
else:
    st.caption("Sin fecha de próxima publicación de CPI disponible ahora mismo.")
