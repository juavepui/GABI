"""Spanish label and plain-language help for every metric GABI shows: the single source for every interface."""

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
        "label": "Cobertura ponderada",
        "help": "Disponibilidad de las 13 métricas puntuables, ponderada por los pesos de sus bloques, "
                "en escala 0–100. 100 = todas presentes. No mide apoyo estadístico ni probabilidad futura; "
                "esa dimensión se muestra aparte como Confianza de evidencia (BAJA/MEDIA/ALTA).",
    },
}
