import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import pandas as pd
import streamlit as st

from gabi import config, screener

st.set_page_config(page_title="Configuración — GABI", page_icon="⚙️", layout="wide")
st.title("⚙️ Configuración")

st.markdown(
    "Los datos se cachean en `data/gabi.db`. Los fundamentales de Yahoo Finance se consideran "
    f"frescos durante **{config.CACHE_MAX_AGE_HOURS} horas**; los precios se refrescan cuando hay "
    f"un día de mercado más reciente sin descargar. Los datos oficiales de **SEC EDGAR** (ROIC, "
    f"crecimiento a 3 años, enlaces a 10-K/10-Q) se consideran frescos "
    f"**{config.EDGAR_CACHE_MAX_AGE_HOURS // 24} días** — cambian mucho menos a menudo, pero la "
    "primera descarga es más lenta porque la SEC es más estricta con el ritmo de peticiones."
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

force = st.checkbox(
    "Forzar re-descarga aunque los datos estén frescos", value=False,
    help="Ignora la caché de 24h y vuelve a pedir todo a Yahoo Finance. Úsalo solo si "
         "sospechas que los datos están mal, ya que tarda más y consume más peticiones.",
)


def _run_refresh(symbols, force_flag):
    yf_bar = st.progress(0.0, text="Yahoo Finance: descargando precios...")
    edgar_bar = st.progress(0.0, text="SEC EDGAR: en espera...")

    def yf_progress_cb(done, total, sym):
        pct = done / total if total else 1.0
        yf_bar.progress(min(pct, 1.0), text=f"Yahoo Finance — fundamentales: {done}/{total} ({sym})")

    def edgar_progress_cb(done, total, sym):
        pct = done / total if total else 1.0
        edgar_bar.progress(min(pct, 1.0), text=f"SEC EDGAR — informes oficiales: {done}/{total} ({sym})")

    with st.spinner("Actualizando..."):
        result = screener.refresh_data(
            symbols, force=force_flag, progress_cb=yf_progress_cb, edgar_progress_cb=edgar_progress_cb,
        )
    yf_bar.progress(1.0, text="Yahoo Finance: completado")
    edgar_bar.progress(1.0, text="SEC EDGAR: completado")
    return result


if st.button("🔄 Actualizar datos", type="primary"):
    uni = screener.get_universe(limit=limit)
    st.session_state["last_refresh_result"] = _run_refresh(uni["symbol"].tolist(), force)

st.divider()

result = st.session_state.get("last_refresh_result")
if result is not None:
    st.subheader("Resultado de la última actualización")
    st.success(
        f"Precios refrescados: {'sí' if result['price_refreshed'] else 'no (ya estaban al día)'} · "
        f"Fundamentales Yahoo actualizados: {result['fundamentals_refreshed']} · "
        f"Datos SEC EDGAR actualizados: {result.get('edgar_refreshed', 0)} · "
        f"Empresas con fallos: {len(result['failed'])}"
    )

    failed = result["failed"]
    if not failed:
        st.info("✅ Ninguna empresa ha fallado en esta actualización.")
    else:
        rows = [
            {"symbol": sym, "etapa": stage, "motivo": reason}
            for sym, stages in failed.items()
            for stage, reason in stages.items()
        ]
        failed_df = pd.DataFrame(rows)

        st.error(f"❌ {failed_df['symbol'].nunique()} empresas con algún fallo al actualizar")

        summary = (
            failed_df.groupby("motivo")["symbol"]
            .apply(lambda s: sorted(set(s)))
            .reset_index()
            .rename(columns={"symbol": "empresas"})
        )
        summary["nº empresas"] = summary["empresas"].apply(len)
        summary = summary.sort_values("nº empresas", ascending=False)

        n_motivos = len(summary)
        if n_motivos == 1:
            st.caption("Todos los fallos comparten el mismo motivo:")
        else:
            st.caption(f"Los fallos se agrupan en {n_motivos} motivos distintos:")

        for _, r in summary.iterrows():
            with st.expander(f"{r['motivo']} — {r['nº empresas']} empresas"):
                st.write(", ".join(r["empresas"]))

        if any("límite de peticiones" in m.lower() for m in summary["motivo"]):
            st.caption(
                "💡 Si muchos fallos son por 'límite de peticiones', Yahoo Finance te está "
                "limitando temporalmente. Espera unos minutos y usa 'Reintentar solo los fallidos'."
            )

        if st.button("🔁 Reintentar solo los fallidos"):
            retry_symbols = list(failed.keys())
            st.session_state["last_refresh_result"] = _run_refresh(retry_symbols, force_flag=True)
            st.rerun()

st.divider()
st.subheader("Pesos del score compuesto")
st.caption("Se guardan como valores por defecto para el Screener (puedes seguir ajustándolos allí).")

weights = config.load_weights()
col1, col2, col3 = st.columns(3)
with col1:
    w_value = st.slider("Value", 0, 100, int(weights.get("value", 0.35) * 100), help="Peso de lo barata que está la empresa (PER, PEG, P/VC, P/Ventas, EV/EBITDA).")
with col2:
    w_quality = st.slider("Quality", 0, 100, int(weights.get("quality", 0.35) * 100), help="Peso de la calidad de los fundamentales (rentabilidad, márgenes, deuda, crecimiento).")
with col3:
    w_momentum = st.slider("Momentum", 0, 100, int(weights.get("momentum", 0.30) * 100), help="Peso de las señales técnicas de tendencia alcista (medias móviles, RSI, fuerza relativa).")

if st.button("💾 Guardar pesos por defecto"):
    total = max(w_value + w_quality + w_momentum, 1)
    new_weights = {
        "value": w_value / total,
        "quality": w_quality / total,
        "momentum": w_momentum / total,
    }
    config.save_weights(new_weights)
    st.success("Pesos guardados.")

st.divider()
st.subheader("🌐 API key de FRED (panel macro)")
st.markdown(
    "El [🌐 Panel Macro](/Panel_Macro) (tipos, inflación, curva de tipos, crédito...) necesita una API "
    "key gratuita de FRED — alta inmediata, sin tarjeta: "
    "[fred.stlouisfed.org/docs/api/api_key.html](https://fred.stlouisfed.org/docs/api/api_key.html)."
)
current_key = config.load_fred_key()
new_key = st.text_input(
    "API key de FRED", value=current_key or "", type="password",
    help="Se guarda localmente en data/fred_api_key.txt (no se sube a ningún sitio; ese archivo está "
         "excluido del control de versiones).",
)
if st.button("💾 Guardar API key de FRED"):
    if new_key.strip():
        config.save_fred_key(new_key)
        st.success("Clave guardada. Ve al Panel Macro para descargar los datos.")
    else:
        st.error("Pega una clave antes de guardar.")
