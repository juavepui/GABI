"""Ayudas de presentación para la interfaz: glosario de métricas en español
(para tooltips), traducción de sectores GICS y color-coding rojo→verde de
las tablas. Vive aquí (y no en app/) para que tanto el Screener como la
Ficha de empresa compartan una única fuente de verdad."""
import pandas as pd

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


METRIC_INFO = {
    "name": {"label": "Empresa", "help": "Nombre de la empresa."},
    "sector": {"label": "Sector", "help": "Sector GICS al que pertenece la empresa."},
    "market_cap": {
        "label": "Cap. mercado (mil M$)",
        "help": "Valor total de la empresa en bolsa (precio de la acción × nº de acciones), en miles de millones de dólares.",
    },
    "pe": {
        "label": "PER",
        "help": "Precio/Beneficio: veces que el precio de la acción contiene el beneficio anual por acción. "
                "Más bajo suele indicar que está más barata (pero también puede reflejar problemas de crecimiento).",
    },
    "peg": {
        "label": "PEG",
        "help": "PER ajustado por el crecimiento esperado de beneficios. Por debajo de 1 se suele considerar atractivo.",
    },
    "pb": {
        "label": "P/VC",
        "help": "Precio / Valor Contable: cuánto paga el mercado por cada dólar de patrimonio neto contable de la empresa.",
    },
    "ps": {
        "label": "P/Ventas",
        "help": "Precio / Ventas: capitalización de mercado dividida entre los ingresos anuales.",
    },
    "ev_ebitda": {
        "label": "EV/EBITDA",
        "help": "Valor de empresa entre EBITDA (beneficio operativo antes de intereses, impuestos y amortizaciones). "
                "Permite comparar empresas con distinto nivel de deuda.",
    },
    "net_debt_to_ebitda": {
        "label": "Deuda neta/EBITDA",
        "help": "Deuda a largo plazo menos caja, dividido entre EBITDA. Mide en cuántos años de beneficio operativo "
                "bruto podría la empresa pagar toda su deuda neta — cuanto más bajo, menos apalancada.",
    },
    "shares_outstanding": {
        "label": "Nº de acciones",
        "help": "Acciones en circulación conocidas en la fecha consultada — se usa junto al precio para calcular "
                "la capitalización de mercado de esa fecha, sin usar el nº de acciones de hoy.",
    },
    "fundamentals_period_end": {
        "label": "Cierre del ejercicio usado",
        "help": "Fecha de cierre del último ejercicio fiscal anual (10-K) que ya se conocía en la fecha consultada "
                "— el origen de ROIC, márgenes y crecimiento de esa fila.",
    },
    "roe": {
        "label": "ROE (%)",
        "help": "Rentabilidad sobre el patrimonio neto (Return on Equity): beneficio generado por cada dólar de capital propio invertido.",
    },
    "roa": {
        "label": "ROA (%)",
        "help": "Rentabilidad sobre activos (Return on Assets): eficiencia de la empresa usando todos sus activos para generar beneficio.",
    },
    "roic": {
        "label": "ROIC (%)",
        "help": "Rentabilidad sobre el capital invertido (Return on Invested Capital), aproximada a partir de datos oficiales de "
                "SEC EDGAR: beneficio neto entre (patrimonio neto + deuda a largo plazo). Mide si la empresa gana más de lo que "
                "le cuesta el capital que usa — clave para saber si tiene una ventaja competitiva (moat) real. Puede faltar si "
                "la empresa no reporta esas partidas con las etiquetas XBRL habituales (ej. empresas casi sin deuda a largo plazo).",
    },
    "operating_margin": {
        "label": "Margen operativo (%)",
        "help": "Porcentaje de las ventas que queda como beneficio operativo, antes de intereses e impuestos.",
    },
    "gross_margin": {
        "label": "Margen bruto (%)",
        "help": "Porcentaje de las ventas que queda tras descontar el coste directo de producir el producto o servicio.",
    },
    "profit_margin": {
        "label": "Margen neto (%)",
        "help": "Porcentaje de las ventas que se convierte finalmente en beneficio neto.",
    },
    "debt_to_equity": {
        "label": "Deuda/Patrimonio",
        "help": "Deuda total dividida entre el patrimonio neto. Cuanto más alto, más apalancada (endeudada) está la empresa.",
    },
    "current_ratio": {
        "label": "Ratio corriente",
        "help": "Activo corriente entre pasivo corriente: capacidad de pagar deudas a corto plazo. Por encima de 1 se considera saludable.",
    },
    "revenue_growth_yoy": {
        "label": "Crec. ingresos YoY (%)",
        "help": "Crecimiento de los ingresos respecto al mismo periodo del año anterior (Year over Year).",
    },
    "earnings_growth_yoy": {
        "label": "Crec. beneficios YoY (%)",
        "help": "Crecimiento del beneficio respecto al mismo periodo del año anterior.",
    },
    "revenue_growth_ttm_yoy": {
        "label": "Crec. ingresos TTM (%)",
        "help": "Crecimiento interanual de los ingresos de los últimos 12 meses (Trailing Twelve Months), calculado a partir "
                "de los informes trimestrales. Puede faltar si Yahoo Finance no ofrece suficiente histórico trimestral.",
    },
    "free_cashflow": {
        "label": "Flujo de caja libre",
        "help": "Efectivo que genera la empresa después de cubrir sus gastos operativos e inversiones.",
    },
    "revenue_cagr_3y": {
        "label": "Crec. ingresos 3A CAGR (%)",
        "help": "Crecimiento anualizado de los ingresos en los últimos 3 años fiscales completos, calculado a partir de los "
                "10-K oficiales en SEC EDGAR (más fiable que el histórico trimestral limitado de Yahoo Finance).",
    },
    "fcf_cagr_3y": {
        "label": "Crec. FCF 3A CAGR (%)",
        "help": "Crecimiento anualizado del flujo de caja libre (flujo de caja operativo menos inversión en capital, "
                "CAPEX) en los últimos 3 años fiscales completos, según los 10-K oficiales en SEC EDGAR.",
    },
    "beta": {
        "label": "Beta (Yahoo Finance)",
        "help": "Volatilidad de la acción respecto al mercado en general, tal y como la calcula Yahoo Finance (metodología "
                "no publicada). 1 = se mueve igual que el mercado; por encima de 1 = más volátil. Compárala con 'Beta "
                "(vs S&P 500)', que es la que calcula GABI de forma transparente a partir del histórico cacheado.",
    },
    "price": {"label": "Precio", "help": "Último precio de cierre disponible."},
    "price_vs_sma50": {
        "label": "vs SMA50 (%)",
        "help": "Diferencia porcentual entre el precio actual y su media móvil de 50 sesiones. Positivo indica tendencia alcista de corto plazo.",
    },
    "price_vs_sma200": {
        "label": "vs SMA200 (%)",
        "help": "Diferencia porcentual entre el precio actual y su media móvil de 200 sesiones. Positivo indica tendencia alcista de largo plazo.",
    },
    "rsi14": {
        "label": "RSI14",
        "help": "Índice de Fuerza Relativa a 14 sesiones. Por debajo de 30 sugiere sobreventa, por encima de 70 sobrecompra. "
                "Zona considerada sana para entrar: 45-65.",
    },
    "momentum_6m": {"label": "Momentum 6M (%)", "help": "Variación del precio en los últimos ~6 meses."},
    "momentum_12m": {"label": "Momentum 12M (%)", "help": "Variación del precio en los últimos ~12 meses."},
    "rel_strength_6m": {
        "label": "Fuerza relativa 6M (%)",
        "help": "Diferencia de rentabilidad a 6 meses respecto al S&P 500 (ETF SPY). Positivo significa que lo está batiendo.",
    },
    "golden_cross_recent": {
        "label": "Golden cross reciente",
        "help": "La media móvil de 50 sesiones ha cruzado por encima de la de 200 en los últimos 20 días de mercado "
                "— señal técnica alcista clásica.",
    },
    "volatility": {
        "label": "Volatilidad anualizada (%)",
        "help": "Dispersión de los retornos diarios de la acción, anualizada. Más alta = movimientos de precio más "
                "bruscos (más riesgo), en ambas direcciones.",
    },
    "max_drawdown": {
        "label": "Máximo drawdown (%)",
        "help": "Mayor caída desde un máximo hasta un mínimo posterior en el histórico de precios cacheado. Cuanto "
                "más cerca de 0%, menor ha sido la peor caída.",
    },
    "sharpe_ratio": {
        "label": "Sharpe Ratio",
        "help": "Retorno anualizado por encima del tipo libre de riesgo, dividido entre la volatilidad total. Cuanto "
                "más alto, mejor retorno por cada unidad de riesgo asumido.",
    },
    "sortino_ratio": {
        "label": "Sortino Ratio",
        "help": "Como el Sharpe Ratio, pero solo penaliza la volatilidad a la baja (las subidas fuertes no cuentan "
                "como 'riesgo'). Más alto = mejor.",
    },
    "beta_calc": {
        "label": "Beta (vs S&P 500)",
        "help": "Sensibilidad del precio de la acción a los movimientos del S&P 500, calculada por GABI a partir del "
                "histórico cacheado (no es el beta de Yahoo Finance). 1 = se mueve igual que el mercado; >1 = más "
                "volátil que el mercado; <1 = más defensiva.",
    },
    "alpha": {
        "label": "Alpha anualizado (%)",
        "help": "Retorno de la acción por encima de lo que explicaría su beta frente al S&P 500 (modelo CAPM). "
                "Positivo = ha batido a lo que le 'correspondía' dado su riesgo de mercado.",
    },
    "win_rate_monthly": {
        "label": "Win rate mensual (%)",
        "help": "Porcentaje de meses con retorno positivo en el histórico de precios cacheado.",
    },
    "dividend_yield": {
        "label": "Rentabilidad por dividendo (%)",
        "help": "Dividendo anual entre precio de la acción. 0% no es necesariamente malo: muchas empresas de "
                "crecimiento reinvierten el beneficio en vez de repartir dividendo.",
    },
    "avg_volume": {
        "label": "Volumen medio diario (3M)",
        "help": "Número medio de acciones negociadas al día en los últimos 3 meses — indicador de liquidez: cuanto "
                "más alto, más fácil entrar y salir de la posición sin mover el precio.",
    },
    "value_score": {
        "label": "Value",
        "help": "Score 0-100 de PER, P/VC y EV/EBITDA frente a otras de su sector. "
                "100 = la más barata de su sector.",
    },
    "quality_score": {
        "label": "Quality",
        "help": "Score 0-100 de ROIC, margen operativo y crecimiento a 3 años de ingresos y FCF. "
                "100 = los mejores fundamentales de su sector.",
    },
    "quality_persistence_score": {
        "label": "Persistencia calidad",
        "help": "Fracción de años disponibles con ROIC, margen operativo y conversión de FCF positivos. "
                "Es una métrica descriptiva point-in-time y todavía no entra en el Composite.",
    },
    "roic_persistence_mean": {
        "label": "ROIC medio histórico",
        "help": "Media anual del ROIC aproximado disponible hasta la fecha reconstruida.",
    },
    "roic_persistence_std": {
        "label": "Variabilidad ROIC",
        "help": "Desviación estándar anual del ROIC aproximado; no se calcula estabilidad si faltan años.",
    },
    "roic_years": {"label": "Años ROIC", "help": "Número de ejercicios anuales de ROIC disponibles hasta la fecha."},
    "operating_margin_persistence_mean": {
        "label": "Margen operativo medio",
        "help": "Media anual del margen operativo disponible hasta la fecha reconstruida.",
    },
    "operating_margin_persistence_std": {
        "label": "Variabilidad margen",
        "help": "Desviación estándar anual del margen operativo disponible.",
    },
    "operating_margin_years": {
        "label": "Años margen",
        "help": "Número de ejercicios anuales de margen operativo disponibles.",
    },
    "fcf_conversion_mean": {
        "label": "Conversión FCF media",
        "help": "Media anual de FCF dividido por ingresos; métrica descriptiva, no parte del Composite.",
    },
    "fcf_years": {"label": "Años FCF", "help": "Número de ejercicios anuales con conversión de FCF disponible."},
    "revenue_per_share_cagr": {
        "label": "Ventas por acción CAGR",
        "help": "Crecimiento anualizado histórico de ventas por acción con los ejercicios disponibles.",
    },
    "implied_fcf_growth": {
        "label": "Crecimiento FCF implícito",
        "help": "Crecimiento anual de FCF que el reverse DCF necesita para justificar el valor de empresa observado. "
                "Supuestos fijos: descuento 9%, crecimiento terminal 2,5% y 5 años.",
    },
    "expectations_gap": {
        "label": "Brecha expectativas",
        "help": "FCF CAGR histórico de 3 años menos crecimiento implícito en precio. Es descriptivo y no entra en el Composite.",
    },
    "expectations_discount_rate": {"label": "Descuento DCF", "help": "Tasa de descuento fija usada por el reverse DCF."},
    "expectations_terminal_growth": {"label": "Crecimiento terminal", "help": "Crecimiento terminal fijo usado por el reverse DCF."},
    "momentum_score": {
        "label": "Momentum",
        "help": "Score 0-100 de momentum a 12 meses, fuerza relativa a 6 meses y precio frente a SMA200. "
                "100 = el momentum más fuerte de su sector.",
    },
    "risk_score": {
        "label": "Risk",
        "help": "Score 0-100 de deuda, volatilidad y máximo drawdown frente a otras de su sector. "
                "100 = la más 'segura' de su sector — no confundir con mejor "
                "retorno esperado, solo menor riesgo.",
    },
    "composite_score": {
        "label": "Composite",
        "help": "Media ponderada de Value, Quality, Momentum y Risk según los pesos configurados. Es el score final "
                "usado para ordenar el ranking.",
    },
    "metrics_available": {"label": "Datos", "help": "Número de métricas disponibles de las 13 que puntúan."},
    "metrics_possible": {"label": "Datos posibles", "help": "Número total de métricas que puntúan."},
    "score_coverage": {"label": "Cobertura %", "help": "Porcentaje de las 13 métricas puntuables disponibles."},
    "next_earnings_days": {
        "label": "Próx. earnings (días)",
        "help": "Días hasta la próxima publicación de resultados conocida (fuente: Yahoo Finance). La "
                "fecha suele ser una estimación hasta que la empresa la confirma -- abre la Ficha de la "
                "empresa para ver si está confirmada o estimada. Contexto temporal: no entra en el "
                "Composite Score.",
    },
    "confidence": {
        "label": "Confidence",
        "help": "Cuánto fiarse del Composite — NO cuánto de atractiva es la empresa (eso ya lo dice el "
                "Composite). Una empresa con solo 1 de las 4 métricas de Quality disponible puede sacar el "
                "mismo Quality score que otra con las 4, si esa única métrica es muy buena — Confidence baja "
                "en ese caso para avisar de que ese score se apoya en poco dato. 100 = las 13 métricas "
                "presentes; baja más cuanto más pesan (según tus sliders) los bloques con datos ausentes.",
    },
}

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
