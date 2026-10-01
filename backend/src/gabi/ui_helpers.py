"""Ayudas de presentación para la interfaz: glosario de métricas en español
(para tooltips), traducción de sectores GICS y color-coding rojo→verde de
las tablas. Vive aquí (y no en app/) para que tanto el Screener como la
Ficha de empresa compartan una única fuente de verdad."""
import pandas as pd

from gabi.domain.market.metric_info import METRIC_INFO  # noqa: F401 (public name kept)

# El indicador nativo de "ejecutando" de Streamlit (data-testid="stStatusWidget")
# aparece por defecto arriba a la derecha y es fácil no verlo. Streamlit no
# tiene una opción de configuración para moverlo, así que se reposiciona por
# CSS al centro de la pantalla y se agranda un poco para que se note.
CUSTOM_CSS = """
<style>
div[data-testid="stStatusWidget"] {
    position: fixed !important;
    top: 50% !important;
    left: 50% !important;
    transform: translate(-50%, -50%) scale(2.5) !important;
    z-index: 9999 !important;
    background: rgba(120, 120, 120, 0.15);
    border-radius: 16px;
    padding: 16px 24px;
    box-shadow: 0 4px 24px rgba(0, 0, 0, 0.2);
}

/* Streamlit deja bastante margen de sobra en la barra lateral por defecto;
   se estrecha para dejar más sitio a las tablas. El !important fija el
   ancho, así que de paso impide arrastrarla a mano (el tirador de borde de
   Streamlit deja de tener efecto) — si en algún momento se prefiere volver
   a poder arrastrarla, basta con quitar esta regla entera. */
section[data-testid="stSidebar"] {
    width: 230px !important;
}
</style>
"""


def inject_custom_css():
    import streamlit as st
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# Columnas cuyo valor crudo es una fracción (0.09 = 9%) — se multiplican por
# 100 solo para presentarlas en pantalla.
FRACTION_COLUMNS = {
    "roe", "roa", "roic", "operating_margin", "gross_margin", "profit_margin",
    "revenue_growth_yoy", "earnings_growth_yoy", "revenue_growth_ttm_yoy",
    "revenue_cagr_3y", "fcf_cagr_3y",
    "quality_persistence_score", "roic_persistence_mean", "roic_persistence_std",
    "operating_margin_persistence_mean", "operating_margin_persistence_std", "fcf_conversion_mean",
    "revenue_per_share_cagr",
    "implied_fcf_growth", "historical_fcf_cagr", "expectations_gap",
    "price_vs_sma50", "price_vs_sma200", "momentum_6m", "momentum_12m", "rel_strength_6m",
    "volatility", "max_drawdown", "alpha", "win_rate_monthly", "dividend_yield", "score_coverage",
}

# Las 11 categorías estándar GICS (fuente: universe.py).
SECTOR_ES = {
    "Information Technology": "Tecnología de la información",
    "Health Care": "Salud",
    "Financials": "Financiero",
    "Consumer Discretionary": "Consumo discrecional",
    "Communication Services": "Servicios de comunicación",
    "Industrials": "Industria",
    "Consumer Staples": "Consumo básico",
    "Energy": "Energía",
    "Utilities": "Utilities (servicios públicos)",
    "Real Estate": "Inmobiliario",
    "Materials": "Materiales",
}

SCORE_COLUMNS = {"value_score", "quality_score", "momentum_score", "risk_score", "composite_score", "confidence"}


def translate_sector(sector_en):
    if sector_en is None or (isinstance(sector_en, float) and pd.isna(sector_en)):
        return sector_en
    return SECTOR_ES.get(sector_en, sector_en)


def format_metric_value(metric: str, value) -> str:
    """Formatea un valor crudo para mostrarlo en una tabla/detalle, en español."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    if isinstance(value, bool):
        return "Sí" if value else "No"
    if metric == "market_cap":
        return f"{value / 1e9:.1f} mil M$"
    if metric in ("avg_volume", "shares_outstanding"):
        return f"{value / 1e6:.1f}M acciones" + ("/día" if metric == "avg_volume" else "")
    if metric == "fundamentals_period_end":
        return str(value)
    if metric in FRACTION_COLUMNS:
        return f"{value * 100:.1f}%"
    return f"{value:.2f}"


def gradient_style(pct) -> str:
    """CSS de fondo rojo→ámbar→verde para una celda, dado un percentil 0-100
    (100 = mejor dentro del universo analizado)."""
    if pct is None or (isinstance(pct, float) and pd.isna(pct)):
        return ""
    pct = max(0.0, min(100.0, float(pct)))
    if pct <= 50:
        hue = (pct / 50) * 40  # 0 rojo -> 40 ámbar
    else:
        hue = 40 + ((pct - 50) / 50) * 102  # 40 ámbar -> 142 verde
    return f"background-color: hsl({hue:.0f}, 65%, 40%); color: white"


def build_color_basis(df: pd.DataFrame, columns) -> pd.DataFrame:
    """DataFrame con la misma forma que df[columns] pero con el percentil
    0-100 (100=mejor) que debe usarse como base del color de cada celda.

    Para las columnas de score usa el propio valor (ya está en 0-100); para
    el resto usa la columna '<col>_pct' que calcula scoring.build_scores.
    Si no hay percentil disponible, la celda queda sin color (NaN)."""
    basis = pd.DataFrame(index=df.index)
    for col in columns:
        if col in SCORE_COLUMNS and col in df.columns:
            basis[col] = df[col]
        elif col + "_pct" in df.columns:
            basis[col] = df[col + "_pct"]
        else:
            basis[col] = float("nan")
    return basis
