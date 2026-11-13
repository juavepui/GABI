"""Spanish label and plain-language help for every metric GABI shows: the single source for every interface."""

import math

METRIC_INFO = {
    "name": {"label": "Empresa", "help": "Nombre de la empresa."},
    "sector": {"label": "Sector", "help": "Sector GICS al que pertenece la empresa."},
    "market_cap": {
        "label": "Cap. mercado (mil M$)",
        "help": "Lo que vale la empresa en bolsa: precio de la acción × número de acciones, en miles de millones "
                "de dólares. Sirve para saber si es grande, mediana o pequeña.",
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
        "help": "Precio / valor contable: cuánto se paga en bolsa por cada dólar que la empresa vale «en libros» "
                "(lo que tiene menos lo que debe). Más bajo suele indicar que está más barata, aunque en "
                "empresas de servicios o tecnología el valor en libros dice poco.",
    },
    "ps": {
        "label": "P/Ventas",
        "help": "Precio / Ventas: capitalización de mercado dividida entre los ingresos anuales.",
    },
    "ev_ebitda": {
        "label": "EV/EBITDA",
        "help": "Cuántas veces paga el precio de toda la empresa, incluida su deuda (EV), el beneficio que "
                "genera su negocio antes de intereses, impuestos y amortizaciones (EBITDA). Como incluye la "
                "deuda, sirve para comparar empresas muy endeudadas con otras que no lo están. Más bajo suele "
                "ser más barato.",
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
        "help": "Rentabilidad sobre los fondos propios (ROE): cuánto beneficio gana la empresa por cada dólar "
                "que han puesto sus accionistas. Más alto suele ser mejor, aunque mucha deuda también lo infla.",
    },
    "roa": {
        "label": "ROA (%)",
        "help": "Rentabilidad sobre activos (Return on Assets): eficiencia de la empresa usando todos sus activos para generar beneficio.",
    },
    "roic": {
        "label": "ROIC (%)",
        "help": "Rentabilidad del capital invertido (ROIC): cuánto gana la empresa por cada dólar invertido en "
                "el negocio, venga de los accionistas o de deuda. Si gana más de lo que le cuesta ese dinero, "
                "suele tener alguna ventaja difícil de copiar. GABI lo aproxima con las cuentas oficiales de la "
                "SEC: beneficio neto / (fondos propios + deuda a largo plazo), sin ajustes fiscales; no es el "
                "ROIC «de manual». Puede faltar si la empresa no publica esas partidas de la forma habitual.",
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
        "help": "Deuda total dividida entre los fondos propios. Cuanto más alta, más depende la empresa del "
                "dinero prestado, y peor lo puede pasar si sube el tipo de interés o caen sus ventas.",
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
        "help": "Caja libre (FCF): el dinero que le queda a la empresa tras pagar sus gastos y sus inversiones. "
                "Es lo que puede usar para repartir dividendos, recomprar acciones o pagar deuda.",
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
    "shares_dilution_yoy": {"label": "Dilución acciones YoY (%)", "help": "Cambio interanual de acciones en circulación según hechos SEC ya publicados. Positivo diluye; negativo indica reducción."},
    "buyback_yield": {"label": "Rentabilidad recompra (%)", "help": "Recompras anuales divulgadas divididas por la capitalización de mercado de la fecha. Puede faltar si la empresa no lo etiqueta."},
    "capex_to_ocf": {"label": "CAPEX / flujo operativo (%)", "help": "Inversión anual en inmovilizado frente al flujo de caja operativo; mide reinversión orgánica cuando ambas partidas están disponibles."},
    "acquisitions_latest": {"label": "Adquisiciones último año", "help": "Pagos anuales por adquisiciones divulgados en SEC EDGAR. No se interpreta como creación de valor por sí solo."},
    "capital_allocation_coverage": {"label": "Cobertura asignación", "help": "Número de las cinco señales de asignación de capital con datos point-in-time; los faltantes no se rellenan con cero."},
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
    "momentum_6m": {"label": "Momentum 6M (%)", "help": "Cuánto ha subido o bajado el precio en los últimos 6 meses aproximadamente."},
    "momentum_12m": {"label": "Momentum 12M (%)", "help": "Cuánto ha subido o bajado el precio en los últimos 12 meses aproximadamente."},
    "rel_strength_6m": {
        "label": "Fuerza relativa 6M (%)",
        "help": "Diferencia de rentabilidad a 6 meses respecto al S&P 500 (ETF SPY). Positivo significa que lo está batiendo.",
    },
    "golden_cross_recent": {
        "label": "Golden cross reciente",
        "help": "Cruce dorado: en los últimos 20 días de bolsa, la media del precio de 50 días ha pasado por "
                "encima de la media de 200 días. Es una señal clásica del análisis técnico de que la tendencia "
                "mejora; no es fiable por sí sola.",
    },
    "volatility": {
        "label": "Volatilidad anualizada (%)",
        "help": "Cuánto se mueve el precio de un día a otro, expresado como movimiento típico en un año, con "
                "todos los precios guardados (la ficha dice desde cuándo). Más alta = subidas y bajadas más "
                "bruscas, es decir, más riesgo y más sustos.",
    },
    "max_drawdown": {
        "label": "Máximo drawdown (%)",
        "help": "La mayor caída desde un máximo hasta el punto más bajo posterior, con todos los precios "
                "guardados. Por ejemplo, −40 % significa que en el peor momento quien compró en el máximo perdía "
                "un 40 %. La ficha y Comparar indican las fechas y la caída de los últimos 5 y 3 años. Más cerca "
                "de 0 % es mejor.",
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
        "help": "Cuánto se mueve la acción cuando se mueve el mercado (S&P 500), calculado por GABI con los "
                "precios guardados. 1 = igual que el mercado; 1,5 = un 50 % más (si el mercado cae un 10 %, ella "
                "suele caer un 15 %); menos de 1 = más tranquila que el mercado.",
    },
    "alpha": {
        "label": "Alpha anualizado (%)",
        "help": "Rentabilidad extra al año por encima de lo que le «tocaba» por moverse como el mercado (modelo "
                "CAPM). Positiva = lo ha hecho mejor de lo esperado por su riesgo; es pasado y no garantiza el "
                "futuro.",
    },
    "win_rate_monthly": {
        "label": "Win rate mensual (%)",
        "help": "En qué porcentaje de los meses guardados subió el precio.",
    },
    "dividend_yield": {
        "label": "Rentabilidad por dividendo (%)",
        "help": "Dividendo de un año dividido entre el precio de la acción: qué porcentaje de lo invertido "
                "recibirías en dividendos. Un 0 % no es malo por sí mismo: muchas empresas que crecen prefieren "
                "reinvertir el beneficio en lugar de repartirlo.",
    },
    "avg_volume": {
        "label": "Volumen medio diario (3M)",
        "help": "Cuántas acciones se compran y venden de media al día (últimos 3 meses). Cuantas más, más fácil "
                "es comprar o vender sin mover el precio.",
    },
    "value_score": {
        "label": "Valoración (Value)",
        "help": "Nota de 0 a 100 sobre si la acción está barata frente a otras de su sector, según su PER, su "
                "precio/valor contable y su EV/EBITDA. 100 = la más barata de su sector. Barata no siempre "
                "significa ganga: a veces lo está por buenos motivos.",
    },
    "quality_score": {
        "label": "Calidad (Quality)",
        "help": "Nota de 0 a 100 sobre lo buena que es la empresa como negocio frente a las de su sector: "
                "rentabilidad del capital (ROIC), margen operativo y cuánto han crecido sus ventas y su caja "
                "libre en 3 años. 100 = el mejor negocio de su sector según estos datos.",
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
        "label": "Momentum (tendencia)",
        "help": "Nota de 0 a 100 sobre si el precio viene subiendo: subida en 12 meses, subida frente al mercado "
                "en 6 meses y precio frente a su media de 200 días. 100 = la tendencia más fuerte de su sector. "
                "Que haya subido no garantiza que siga subiendo.",
    },
    "risk_score": {
        "label": "Riesgo (Risk)",
        "help": "Nota de 0 a 100 sobre lo tranquila que es la acción frente a las de su sector: poca deuda, "
                "precio que se mueve poco y caídas pequeñas. 100 = la de menos riesgo de su sector. Menos riesgo "
                "no significa más rentabilidad.",
    },
    "composite_score": {
        "label": "Puntuación GABI (Composite)",
        "help": "La nota final de GABI, de 0 a 100: mezcla los cuatro apartados (valoración, calidad, momentum y "
                "riesgo) con los pesos del modelo. Sirve para ordenar el ranking. Más alta es mejor según el "
                "modelo, pero no es la probabilidad de que la acción suba.",
    },
    "metrics_available": {"label": "Datos", "help": "Número de métricas disponibles de las 13 que puntúan."},
    "metrics_possible": {"label": "Datos posibles", "help": "Número total de métricas que puntúan."},
    "score_coverage": {
        "label": "Métricas con dato",
        "help": "Qué parte de los 13 datos que usa la puntuación tiene esta empresa, contándolos todos igual (10 "
                "de 13 = 76,9 %). Para entrar en la cartera propuesta hace falta al menos un 70 %.",
    },
    "next_earnings_days": {
        "label": "Próx. earnings (días)",
        "help": "Días que faltan para que la empresa presente sus próximos resultados (fuente: Yahoo Finance). "
                "Hasta que la empresa la confirma, la fecha suele ser aproximada; la ficha indica cuál es el "
                "caso. Es solo para tenerlo en cuenta: no cuenta para la puntuación.",
    },
    "confidence": {
        "label": "Datos disponibles",
        "help": "Cuántos de los 13 datos que usa la puntuación tiene esta empresa, de 0 a 100, dando más "
                "importancia a los datos de los apartados que más pesan. 100 = los tiene todos. Si es bajo, la "
                "puntuación es menos fiable. No mide si la empresa es buena ni la confianza en las pruebas (eso "
                "es la «Confianza» BAJA/MEDIA/ALTA).",
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


def format_metric_value(metric: str, value) -> str:
    """Formatea un valor crudo para mostrarlo en una tabla/detalle, en español."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
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
