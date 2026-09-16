"""Ayudas de presentación para la interfaz: glosario de métricas en español
(para tooltips), traducción de sectores GICS y color-coding rojo→verde de
las tablas. Vive aquí (y no en app/) para que tanto el Screener como la
Ficha de empresa compartan una única fuente de verdad."""
import pandas as pd

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
        "label": "Beta",
        "help": "Volatilidad de la acción respecto al mercado en general. 1 = se mueve igual que el mercado; por encima de 1 = más volátil.",
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
    "value_score": {
        "label": "Value",
        "help": "Score 0-100 de lo barata que está la empresa frente al resto del universo analizado (PER, PEG, P/VC, "
                "P/Ventas, EV/EBITDA). 100 = la más barata del universo.",
    },
    "quality_score": {
        "label": "Quality",
        "help": "Score 0-100 de la calidad de los fundamentales frente al resto del universo (rentabilidad, márgenes, "
                "deuda, crecimiento). 100 = los mejores fundamentales del universo.",
    },
    "momentum_score": {
        "label": "Momentum",
        "help": "Score 0-100 de las señales técnicas de tendencia alcista frente al resto del universo (medias móviles, "
                "RSI, fuerza relativa). 100 = el momentum más fuerte del universo.",
    },
    "composite_score": {
        "label": "Composite",
        "help": "Media ponderada de Value, Quality y Momentum según los pesos configurados. Es el score final usado para "
                "ordenar el ranking.",
    },
}

# Columnas cuyo valor crudo es una fracción (0.09 = 9%) — se multiplican por
# 100 solo para presentarlas en pantalla.
FRACTION_COLUMNS = {
    "roe", "roa", "roic", "operating_margin", "gross_margin", "profit_margin",
    "revenue_growth_yoy", "earnings_growth_yoy", "revenue_growth_ttm_yoy",
    "revenue_cagr_3y", "fcf_cagr_3y",
    "price_vs_sma50", "price_vs_sma200", "momentum_6m", "momentum_12m", "rel_strength_6m",
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

SCORE_COLUMNS = {"value_score", "quality_score", "momentum_score", "composite_score"}


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
