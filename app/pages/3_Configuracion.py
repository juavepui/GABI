import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import streamlit as st

from gabi import config, screener

st.set_page_config(page_title="Configuración — GABI", page_icon="⚙️", layout="wide")
st.title("⚙️ Configuración")

st.markdown(
    "Los datos se cachean en `data/gabi.db`. Los fundamentales se consideran "
    f"frescos durante **{config.CACHE_MAX_AGE_HOURS} horas**; los precios se "
    "refrescan cuando hay un día de mercado más reciente sin descargar."
)

st.subheader("Universo")
size_choice = st.radio(
    "Tamaño del universo a analizar",
    options=["Prueba rápida (50 empresas)", "Medio (150 empresas)", "Completo (S&P 500, ~500 empresas)"],
    index=0,
    help="Empieza con un subconjunto pequeño: la primera descarga de fundamentales "
         "tarda bastante porque yfinance no permite pedirlos en batch.",
)
limit_map = {
    "Prueba rápida (50 empresas)": 50,
    "Medio (150 empresas)": 150,
    "Completo (S&P 500, ~500 empresas)": None,
}
limit = limit_map[size_choice]

force = st.checkbox("Forzar re-descarga aunque los datos estén frescos", value=False)

if st.button("🔄 Actualizar datos", type="primary"):
    uni = screener.get_universe(limit=limit)
    symbols = uni["symbol"].tolist()

    progress_bar = st.progress(0.0, text="Descargando precios...")
    status = st.empty()

    def progress_cb(done, total, sym):
        pct = done / total if total else 1.0
        progress_bar.progress(min(pct, 1.0), text=f"Fundamentales: {done}/{total} ({sym})")

    with st.spinner("Actualizando..."):
        result = screener.refresh_data(symbols, force=force, progress_cb=progress_cb)

    progress_bar.progress(1.0, text="Completado")
    st.success(
        f"Precios refrescados: {result['price_refreshed']} · "
        f"Fundamentales actualizados: {result['fundamentals_refreshed']} · "
        f"Fallos: {len(result['failed'])}"
    )
    if result["failed"]:
        with st.expander(f"Ver los {len(result['failed'])} símbolos que fallaron"):
            st.write(result["failed"])

st.divider()
st.subheader("Pesos del score compuesto")
st.caption("Se guardan como valores por defecto para el Screener (puedes seguir ajustándolos allí).")

weights = config.load_weights()
col1, col2, col3 = st.columns(3)
with col1:
    w_value = st.slider("Value", 0, 100, int(weights.get("value", 0.35) * 100))
with col2:
    w_quality = st.slider("Quality", 0, 100, int(weights.get("quality", 0.35) * 100))
with col3:
    w_momentum = st.slider("Momentum", 0, 100, int(weights.get("momentum", 0.30) * 100))

if st.button("💾 Guardar pesos por defecto"):
    total = max(w_value + w_quality + w_momentum, 1)
    new_weights = {
        "value": w_value / total,
        "quality": w_quality / total,
        "momentum": w_momentum / total,
    }
    config.save_weights(new_weights)
    st.success("Pesos guardados.")
