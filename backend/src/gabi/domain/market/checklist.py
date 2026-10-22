"""Checklist fundamental descriptivo (#167).

Evalúa una empresa frente a umbrales explícitos con los 10-K SEC ya presentados,
más precio, consenso o insiders cuando el criterio lo declara. Es informativo:
no puntúa, no filtra ni selecciona en el ranking y no cambia el Composite ni los
motores congelados. Cada ratio usa un único ejercicio fiscal (el último cierre
anual de ingresos o, si falta, de beneficio); un componente de otro ejercicio
deja el criterio sin dato: nunca se mezclan años ni se rellena con cero.
"""
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta

import gabi.domain.market.sec_facts as sec
from gabi.domain.market.metric_sources import METRIC_SOURCES

THRESHOLDS_VERSION = 1
TOLERANCE_DAYS = sec.ALIGNMENT_TOLERANCE_DAYS
GROWTH_YEARS = (10, 5)
TREND_YEARS = 5
ALARM_YEARS = 3
SHARES_YEARS = 5
SHARES_TOLERANCE_DAYS = 120
# Outstanding shares older than the fiscal anchor by more than this are stale.
SHARES_STALE_DAYS = 400
# SEC market cap farther than this from Yahoo's means another share basis
# (share classes, a split missing from the cache, a later issuance).
SHARE_CHECK_TOLERANCE = 0.25
INSIDER_DAYS = 182
INSIDER_SOLD_FRACTION = 0.20
GOODWILL_ASSETS_ALARM = 0.30
CAPEX_SPIKE_POINTS = 0.05
DEBT_GROWTH_ALARM = 0.10
NO_SKIN_FRACTION = 0.01
# Insider ownership comes from Yahoo per listed share class. When the SEC has no total share count
# comparable with the price (usual with several classes), the founder's class may be missing.
INSIDER_CAVEAT_KEYS = frozenset({"insiders_pct", "no_skin_in_the_game"})
FINANCIAL_SECTORS = frozenset({"Financials", "Financial Services"})

# Etiquetas adicionales del checklist. La sincronización SEC explícita las guarda
# junto a TRACKED_TAGS (F2 de #167); un emisor aún no resincronizado, o que no
# declara la partida, deja el criterio sin dato con su motivo.
INTEREST_TAGS = ["InterestExpense", "InterestExpenseNonoperating", "InterestExpenseDebt"]
SBC_TAGS = ["ShareBasedCompensation", "AllocatedShareBasedCompensationExpense"]
TAX_TAGS = ["IncomeTaxExpenseBenefit"]
PRETAX_TAGS = [
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
]
DEBT_CURRENT_TAGS = ["DebtCurrent"]
LT_DEBT_CURRENT_TAGS = ["LongTermDebtCurrent"]
SHORT_BORROWING_TAGS = ["ShortTermBorrowings"]
SHORT_INVESTMENT_TAGS = ["ShortTermInvestments", "MarketableSecuritiesCurrent",
                         "AvailableForSaleSecuritiesDebtSecuritiesCurrent"]
COST_OF_REVENUE_TAGS = ["CostOfRevenue", "CostOfGoodsAndServicesSold"]
GOODWILL_TAGS = ["Goodwill"]
IMPAIRMENT_TAGS = ["GoodwillImpairmentLoss"]
ASSETS_TAGS = ["Assets"]
DEBT_ISSUANCE_TAGS = ["ProceedsFromIssuanceOfLongTermDebt", "ProceedsFromIssuanceOfDebt"]
DIVIDEND_TAGS = ["PaymentsOfDividendsCommonStock", "PaymentsOfDividends"]
# 10-K diluted average shares: reported in total even when outstanding shares are only per class.
DILUTED_SHARES_TAGS = ["WeightedAverageNumberOfDilutedSharesOutstanding"]
BUYBACK_TAGS = ["PaymentsForRepurchaseOfCommonStock", "PaymentsForRepurchaseOfCommonAndPreferredStock"]
CHECKLIST_TAGS = tuple(dict.fromkeys(
    INTEREST_TAGS + SBC_TAGS + TAX_TAGS + PRETAX_TAGS + DEBT_CURRENT_TAGS + LT_DEBT_CURRENT_TAGS
    + SHORT_BORROWING_TAGS + SHORT_INVESTMENT_TAGS + COST_OF_REVENUE_TAGS + GOODWILL_TAGS + IMPAIRMENT_TAGS
    + ASSETS_TAGS + DEBT_ISSUANCE_TAGS + DIVIDEND_TAGS))


@dataclass(frozen=True)
class Rule:
    key: str
    block: str
    label: str
    formula: str
    unit: str
    comparison: str
    default: float | None
    bounds: tuple[float, float] | None
    source: str
    reference: str


_USD = (-1e13, 1e13)
RULES = (
    Rule("revenue_cagr", "Crecimiento", "CAGR de ingresos", "(ingresos / ingresos hace N años)^(1/N) − 1, N = 10 o 5",
         "fraction", ">=", 0.05, (-0.5, 1.0), "sec_10k", "Javier DV"),
    Rule("revenue_growth_stability", "Crecimiento", "Estabilidad del crecimiento",
         "Desviación típica del crecimiento anual de ingresos en los mismos N años", "fraction", "info", None, None,
         "sec_10k", "Javier DV"),
    Rule("cfo_cagr", "Crecimiento", "CAGR del flujo de caja operativo", "(CFO / CFO hace N años)^(1/N) − 1, N = 10 o 5",
         "fraction", ">=", 0.05, (-0.5, 1.0), "sec_10k", "Javier DV"),
    Rule("net_income", "Rentabilidad", "Beneficio neto", "Beneficio neto del ejercicio", "USD", ">", 0.0, _USD,
         "sec_10k", "Javier DV"),
    Rule("gross_margin", "Rentabilidad", "Margen bruto",
         "Beneficio bruto / ingresos (o ingresos − coste de ventas)", "fraction", ">=", 0.30, (-1.0, 1.0),
         "sec_10k", "Javier DV"),
    Rule("net_margin", "Rentabilidad", "Margen neto", "Beneficio neto / ingresos", "fraction", ">=", 0.10,
         (-1.0, 1.0), "sec_10k", "Javier DV, Memorias de Tiburón, La Pizarra de Andrés"),
    Rule("gross_margin_change", "Rentabilidad", "Expansión del margen bruto (5 años)",
         "Margen bruto − margen bruto hace 5 años", "fraction", ">=", 0.0, (-1.0, 1.0), "sec_10k", "Pedro Gutiérrez"),
    Rule("net_margin_change", "Rentabilidad", "Expansión del margen neto (5 años)",
         "Margen neto − margen neto hace 5 años", "fraction", ">=", 0.0, (-1.0, 1.0), "sec_10k", "Pedro Gutiérrez"),
    Rule("roic", "Rentabilidad", "ROIC",
         "EBIT × (1 − tipo efectivo) / (deuda total + patrimonio − caja e inversiones c/p)", "fraction", ">=", 0.10,
         (-1.0, 2.0), "sec_10k", "Javier DV"),
    Rule("net_debt", "Salud", "Deuda neta", "Deuda total − caja − inversiones a corto plazo", "USD", "<=", 0.0, _USD,
         "sec_10k", "Javier DV"),
    Rule("net_debt_to_ebitda", "Salud", "Deuda neta / EBITDA", "Deuda neta / (EBIT + amortizaciones)", "ratio", "<=",
         2.5, (-50.0, 50.0), "sec_10k", "Memorias de Tiburón, La Pizarra de Andrés"),
    Rule("interest_coverage", "Salud", "Cobertura de intereses", "EBIT / gastos por intereses (sin deuda: cumple)",
         "ratio", ">=", 15.0, (0.0, 1000.0), "sec_10k", "Javier DV"),
    Rule("cash_conversion", "Calidad de la caja", "Conversión de caja", "CFO / beneficio neto", "ratio", ">=", 1.0,
         (-10.0, 10.0), "sec_10k", "Javier DV"),
    Rule("cfo_margin", "Calidad de la caja", "Margen de CFO", "CFO / ingresos", "fraction", "info", None, None,
         "sec_10k", "Javier DV"),
    Rule("fcf", "Calidad de la caja", "Flujo de caja libre", "CFO − CAPEX", "USD", ">", 0.0, _USD, "sec_10k",
         "Javier DV"),
    Rule("capex_to_revenue", "Calidad de la caja", "Intensidad de capital", "CAPEX / ingresos", "fraction", "info",
         None, None, "sec_10k", "Javier DV"),
    Rule("shares_change", "Dilución", "Variación del nº de acciones (5 años)",
         "Acciones hoy / acciones hace 5 años − 1, ajustado por splits", "fraction", "<=", 0.0, (-1.0, 5.0),
         "sec_10k", "Javier DV"),
    Rule("sbc_to_net_income", "Dilución", "SBC / beneficio neto", "Remuneración en acciones / beneficio neto",
         "fraction", "<", 0.20, (0.0, 10.0), "sec_10k", "Javier DV"),
    Rule("market_cap", "Valoración", "Capitalización", "Precio × acciones", "USD", "info", None, None,
         "price+sec", "—"),
    Rule("enterprise_value", "Valoración", "Enterprise Value", "Capitalización + deuda total − caja − inversiones c/p",
         "USD", "info", None, None, "price+sec", "—"),
    Rule("pe", "Valoración", "PER", "Capitalización / beneficio neto", "ratio", "<=", 18.0, (0.0, 500.0),
         "price+sec", "La Pizarra de Andrés, Memorias de Tiburón"),
    Rule("forward_pe", "Valoración", "PER forward", "Precio / BPA estimado (consenso Yahoo); cumple si < PER",
         "ratio", "<pe", None, None, "price+yahoo", "La Pizarra de Andrés"),
    Rule("ev_ebitda", "Valoración", "EV / EBITDA", "EV / (EBIT + amortizaciones)", "ratio", "<=", 12.0,
         (0.0, 500.0), "price+sec", "La Pizarra de Andrés, Memorias de Tiburón"),
    Rule("ev_ebit", "Valoración", "EV / EBIT", "EV / EBIT", "ratio", "<=", 12.0, (0.0, 500.0), "price+sec",
         "Memorias de Tiburón"),
    Rule("ev_fcf", "Valoración", "EV / FCF", "EV / (CFO − CAPEX)", "ratio", "<=", 17.0, (0.0, 1000.0), "price+sec",
         "Memorias de Tiburón"),
    Rule("fcf_yield", "Valoración", "FCF yield", "(CFO − CAPEX) / capitalización", "fraction", ">=", 0.04,
         (-1.0, 1.0), "price+sec", "Javier DV"),
    Rule("insiders_pct", "Directiva", "% en manos de directivos", "Acciones de insiders / total (Yahoo)", "fraction",
         ">=", 0.10, (0.0, 1.0), "yahoo", "Memorias de Tiburón, La Pizarra de Andrés"),
    Rule("beta", "Riesgo", "Beta",
         "Covarianza de los rendimientos diarios con el SPY / varianza del SPY (GABI, histórico en caché): "
         "<0,9 defensiva, ≤1,1 neutral", "ratio", "info", None, None, "prices", "La Pizarra de Andrés"),
)
RULES_BY_KEY = {rule.key: rule for rule in RULES}

# Qué mide cada criterio y por qué importa, en lenguaje llano (ayuda contextual de la ficha).
EXPLANATIONS = {
    "revenue_cagr": "Crecimiento medio anual compuesto de las ventas en 10 años (o 5 si no hay más historia). "
                    "Una empresa que no vende más cada año difícilmente aumentará su valor.",
    "revenue_growth_stability": "Cuánto varía el crecimiento de las ventas de un año a otro. Cuanto más bajo, "
                                "más previsible es el negocio; un valor alto indica crecimiento a saltos o cíclico.",
    "cfo_cagr": "Crecimiento medio anual del flujo de caja operativo (el dinero que genera el negocio). Debe "
                "acompañar al de las ventas: si las ventas crecen y la caja no, el crecimiento cuesta dinero.",
    "net_income": "Lo que gana la empresa después de todos los gastos e impuestos. El checklist exige que sea "
                  "positivo: con pérdidas no hay beneficio que valorar.",
    "gross_margin": "Qué parte de cada dólar vendido queda tras pagar lo que cuesta producirlo. Un margen bruto "
                    "alto suele indicar poder de precios o ventaja competitiva.",
    "net_margin": "Qué parte de cada dólar vendido acaba siendo beneficio neto. Mide la rentabilidad final del "
                  "negocio tras todos los costes, intereses e impuestos.",
    "gross_margin_change": "Diferencia entre el margen bruto actual y el de hace 5 años. Si sube, la empresa gana "
                           "poder de precios o eficiencia; si baja, la competencia la presiona.",
    "net_margin_change": "Diferencia entre el margen neto actual y el de hace 5 años. Que se expanda indica que el "
                         "negocio escala: crece más el beneficio que las ventas.",
    "roic": "Rentabilidad que obtiene la empresa sobre todo el capital invertido (deuda y fondos propios, sin la "
            "caja). Por encima del 10 % suele indicar ventaja competitiva; por debajo del coste del capital, "
            "crecer destruye valor.",
    "net_debt": "Deuda total menos caja e inversiones a corto plazo. Si es negativa, la empresa tiene más caja "
                "que deuda (caja neta) y no depende de los bancos.",
    "net_debt_to_ebitda": "Cuántos años de beneficio operativo antes de amortizaciones (EBITDA) harían falta para "
                          "pagar la deuda neta. Por encima de 2,5–3 la deuda empieza a ser un riesgo.",
    "interest_coverage": "Cuántas veces cubre el beneficio operativo (EBIT) los intereses de la deuda. Cuanto más "
                         "alto, más margen tiene la empresa si los beneficios caen o los tipos suben.",
    "cash_conversion": "Flujo de caja operativo dividido entre beneficio neto. Por encima de 1, el beneficio se "
                       "convierte en caja real; muy por debajo puede indicar beneficios contables poco sólidos.",
    "cfo_margin": "Qué parte de las ventas se convierte en caja operativa. Es el equivalente en caja del margen "
                  "neto y es más difícil de maquillar.",
    "fcf": "Caja que queda tras pagar las inversiones necesarias (CAPEX). Es el dinero disponible para dividendos, "
           "recompras, adquisiciones o reducir deuda.",
    "capex_to_revenue": "Qué parte de las ventas se reinvierte en activos fijos. Un negocio que necesita poco CAPEX "
                        "para crecer genera más caja libre.",
    "shares_change": "Cuánto ha cambiado el número de acciones en 5 años, ajustado por splits. Si sube, tu "
                     "participación se diluye; si baja, la empresa recompra acciones y tu parte crece.",
    "sbc_to_net_income": "Remuneración pagada en acciones a empleados frente al beneficio neto. Es un coste real "
                         "que diluye al accionista aunque no salga de la caja; por encima del 20 % es elevado.",
    "market_cap": "Precio de la acción por el número de acciones: lo que el mercado paga hoy por toda la empresa.",
    "enterprise_value": "Capitalización más la deuda neta: lo que costaría comprar la empresa entera asumiendo su "
                        "deuda y quedándose su caja. Se usa en los múltiplos EV.",
    "pe": "Cuántos años de beneficio actual pagas al precio de hoy. Un PER bajo puede indicar que está barata, "
          "o que el mercado espera que el beneficio caiga.",
    "forward_pe": "PER calculado con el beneficio por acción que los analistas esperan para el próximo año. Si es "
                  "menor que el PER actual, el consenso espera que el beneficio crezca.",
    "ev_ebitda": "Enterprise Value dividido entre EBITDA. Compara empresas con distinta deuda; útil en negocios "
                 "con muchas amortizaciones, pero el EBITDA ignora el coste de reponer activos.",
    "ev_ebit": "Enterprise Value dividido entre beneficio operativo (EBIT). Más exigente que EV/EBITDA porque sí "
               "descuenta las amortizaciones.",
    "ev_fcf": "Enterprise Value dividido entre flujo de caja libre: cuántos años de caja libre cuesta la empresa "
              "entera. Es el múltiplo más cercano a la caja que recibe el propietario.",
    "fcf_yield": "Flujo de caja libre entre capitalización: la rentabilidad en caja que obtendrías si fueras dueño "
                 "de toda la empresa. Compárala con lo que paga un bono.",
    "insiders_pct": "Qué parte de las acciones está en manos de directivos y consejeros (Yahoo). Si tienen mucho "
                    "en juego, sus intereses están alineados con los tuyos. En empresas con varias clases de "
                    "acciones puede no contar la clase que controla el fundador.",
    "beta": "Cuánto se mueve la acción frente al mercado: 1 se mueve igual, menos de 1 es más defensiva y más "
            "de 1 amplifica las subidas y las caídas. La calcula GABI frente al SPY, la misma que la ficha muestra "
            "como «Beta calculada frente al SPY». Es informativa, no un criterio de calidad.",
    "dcf_discount_rate": "Rentabilidad anual que exiges a la inversión. Cuanto más alta, menos vale hoy la caja "
                         "futura y más crecimiento tiene que descontar el precio.",
    "dcf_terminal_growth": "Crecimiento anual que se supone para siempre a partir del último año proyectado. Debe "
                           "ser menor que la tasa de descuento y razonable frente a la economía (2–3 %).",
    "dcf_years": "Número de años en los que el FCF crece al ritmo implícito antes de pasar al crecimiento a "
                 "perpetuidad.",
    "dcf_max_implied_growth": "Crecimiento implícito a partir del cual el vídeo considera que el precio exige "
                              "demasiado y la empresa se descarta.",
}

ALARM_EXPLANATIONS = {
    "earnings_outpace_cfo": "El beneficio contable sube pero la caja operativa no le sigue. Puede deberse a "
                            "ventas a crédito o inventario acumulándose: beneficios que aún no son dinero.",
    "debt_up_weak_cfo": "La deuda crece mientras la caja operativa no mejora: la empresa se financia con "
                        "préstamos en vez de con su negocio.",
    "buybacks_with_debt": "La empresa emite deuda por un importe parecido al que gasta en recompras. Recomprar "
                          "con deuda infla el beneficio por acción pero debilita el balance.",
    "dividends_with_debt": "Los dividendos superan el flujo de caja libre mientras la deuda crece: se reparte "
                           "dinero que el negocio no genera.",
    "goodwill": "Mucho goodwill (sobreprecio pagado en adquisiciones) frente a los activos, o deterioros "
                "repetidos: señal de compras caras que luego hay que reconocer como pérdidas.",
    "dilution": "El número de acciones crece o la remuneración en acciones es alta: tu parte de la empresa se "
                "reduce año a año.",
    "executives_selling": "Directivos vendiendo en mercado una parte grande de sus acciones (sin plan 10b5-1 "
                          "programado) en los últimos 6 meses. Si quienes mejor la conocen salen, pregúntate por qué.",
    "no_skin_in_the_game": "Los directivos apenas tienen acciones: cobran sueldo y bonus sin arriesgar su "
                           "patrimonio con el accionista. En empresas con varias clases de acciones el dato de "
                           "Yahoo puede no contar la clase del fundador; revísalo.",
    "blames_external_factors": "Si en las presentaciones de resultados la directiva culpa siempre al entorno "
                               "(divisas, clima, macro) en vez de explicar sus decisiones. Se revisa leyendo las "
                               "conference calls.",
    "adjusted_ebitda": "Las empresas que destacan un EBITDA «ajustado» pueden excluir costes recurrentes para "
                       "mejorar la imagen. GABI usa cifras GAAP; compara con lo que presenta la empresa.",
    "market_share_loss": "Un negocio con supuesta ventaja competitiva que pierde cuota frente a rivales: el foso "
                         "quizá no es tan ancho. Se revisa con datos del sector.",
    "capex_spike": "La inversión (CAPEX) sobre ventas se dispara sin que la caja operativa mejore después: "
                   "inversión que no está dando retorno.",
}
# Period of each criterion source: SEC values use the fiscal anchor; Yahoo values, its capture.
SOURCE_PERIODS = {"sec_10k": "fiscal_year", "price+sec": "fiscal_year", "yahoo": "snapshot",
                  "price+yahoo": "snapshot", "prices": "cached_history"}

# The same concept the company page shows elsewhere with another source, period or formula (#169).
# It is returned as a secondary reference next to the criterion, never mixed into its value.
ALTERNATIVES = {
    "market_cap": ("market_cap", "share_count"),
    "pe": ("pe", "period"),
    "ev_ebitda": ("ev_ebitda", "period"),
    "fcf": ("free_cashflow", "period"),
    "roic": ("roic", "formula"),
    "beta": ("beta", "method"),
}
REFERENCE_KEYS = tuple(metric for metric, _ in ALTERNATIVES.values()) + ("beta_calc",)
DIFFERENCES = {
    "period": "Yahoo usa los últimos 12 meses y el checklist el último 10-K anual. Pueden diferir por el "
              "periodo, por los ajustes de Yahoo (beneficio ajustado, partidas extraordinarias, FCF después de "
              "intereses) y por el número de acciones. Los dos valores no se mezclan.",
    "formula": "Mismo 10-K, distinta fórmula. El ROIC del Composite es beneficio neto / (patrimonio + deuda a "
               "largo plazo); el del checklist, el de los vídeos: EBIT × (1 − tipo efectivo) / (deuda total + "
               "patrimonio − caja e inversiones a corto).",
    "share_count": "Yahoo multiplica el precio por su número de acciones; el checklist usa las acciones de la SEC "
                   "(o la capitalización de Yahoo si no cuadran con el precio).",
    "method": "La beta del checklist la calcula GABI frente al SPY con rendimientos diarios de todo el histórico "
              "en caché. La de Yahoo usa 5 años de rendimientos mensuales con su propia metodología. La "
              "clasificación defensiva/neutral/agresiva usa la de GABI.",
}

FINANCIAL_NOT_APPLICABLE = frozenset({
    "cfo_cagr", "gross_margin", "gross_margin_change", "roic", "net_debt", "net_debt_to_ebitda",
    "interest_coverage", "cash_conversion", "cfo_margin", "fcf", "capex_to_revenue", "enterprise_value",
    "ev_ebitda", "ev_ebit", "ev_fcf", "fcf_yield",
})

DCF_DEFAULTS = {"dcf_discount_rate": 0.09, "dcf_terminal_growth": 0.03, "dcf_years": 10.0,
                "dcf_max_implied_growth": 0.30}
DCF_BOUNDS = {"dcf_discount_rate": (0.01, 0.30), "dcf_terminal_growth": (0.0, 0.10), "dcf_years": (3.0, 20.0),
              "dcf_max_implied_growth": (0.0, 1.0)}
DCF_LABELS = {"dcf_discount_rate": "Tasa de descuento", "dcf_terminal_growth": "Crecimiento a perpetuidad",
              "dcf_years": "Años proyectados", "dcf_max_implied_growth": "Crecimiento implícito descartable"}
DCF_SEARCH = (-0.50, 1.00)

QUALITATIVE = (
    ("moat", "¿Ventaja competitiva identificada?", "Costes, costes de cambio, efecto red o intangibles"),
    ("market_share", "¿Cuota de mercado estable o creciente?", "Verifica el foso con datos, no con narrativa"),
    ("competence", "¿Dentro de tu círculo de competencia?", "¿Puedes preguntar a clientes o proveedores del sector?"),
    ("forecast", "¿Puedes estimar su FCF a 5 años con números?", "Si no, estás apostando, no invirtiendo"),
)


def defaults() -> dict[str, float]:
    values = {rule.key: rule.default for rule in RULES if rule.default is not None}
    return values | DCF_DEFAULTS


def threshold_catalog() -> list[dict]:
    """Every editable threshold with its default, bounds and unit."""
    rows = [{"key": rule.key, "label": rule.label, "block": rule.block, "unit": rule.unit,
             "comparison": rule.comparison, "default": rule.default, "minimum": rule.bounds[0],
             "maximum": rule.bounds[1], "reference": rule.reference, "explanation": EXPLANATIONS[rule.key]}
            for rule in RULES if rule.default is not None and rule.bounds is not None]
    units = {"dcf_years": "count"}
    rows += [{"key": key, "label": DCF_LABELS[key], "block": "DCF inverso", "unit": units.get(key, "fraction"),
              "comparison": "parameter", "default": value, "minimum": DCF_BOUNDS[key][0],
              "maximum": DCF_BOUNDS[key][1], "reference": "Javier DV", "explanation": EXPLANATIONS[key]}
             for key, value in DCF_DEFAULTS.items()]
    return rows


def validate_thresholds(overrides: dict) -> dict[str, float]:
    """Clean user overrides or raise ``ValueError`` with a Spanish message."""
    if not isinstance(overrides, dict):
        raise ValueError("Los umbrales deben ser un objeto clave → valor.")
    known = defaults()
    bounds = {rule.key: rule.bounds for rule in RULES if rule.bounds} | DCF_BOUNDS
    labels = {rule.key: rule.label for rule in RULES} | DCF_LABELS
    cleaned: dict[str, float] = {}
    for key, value in overrides.items():
        if key not in known:
            raise ValueError(f"Umbral desconocido: {key}.")
        if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
            raise ValueError(f"El umbral «{labels[key]}» debe ser un número finito.")
        low, high = bounds[key]
        if not low <= value <= high:
            raise ValueError(f"El umbral «{labels[key]}» debe estar entre {low:g} y {high:g}.")
        if key == "dcf_years" and value != int(value):
            raise ValueError("Los años del DCF deben ser un número entero.")
        cleaned[key] = float(value)
    merged = known | cleaned
    if merged["dcf_terminal_growth"] >= merged["dcf_discount_rate"]:
        raise ValueError("El crecimiento a perpetuidad debe ser menor que la tasa de descuento.")
    return cleaned


# ---------------------------------------------------------------- DCF inverso
def dcf_value_per_share(fcf: float, shares: float, growth: float, *, discount_rate: float, terminal_growth: float,
                        years: int) -> float:
    """Hoja «DCF inverso»: FCF del año t = FCF·(1+g)^(t−1), descontado; valor terminal en el año N."""
    flows = sum(fcf * (1 + growth) ** (year - 1) / (1 + discount_rate) ** year for year in range(1, years + 1))
    terminal = fcf * (1 + growth) ** (years - 1) * (1 + terminal_growth) / (discount_rate - terminal_growth)
    return (flows + terminal / (1 + discount_rate) ** years) / shares


def implied_growth(price: float, fcf: float, shares: float, *, discount_rate: float, terminal_growth: float,
                   years: int) -> tuple[float | None, str | None]:
    """Crecimiento constante del FCF que iguala el valor por acción al precio, o el motivo de su ausencia."""
    def gap(growth: float) -> float:
        return dcf_value_per_share(fcf, shares, growth, discount_rate=discount_rate,
                                   terminal_growth=terminal_growth, years=years) - price

    low, high = DCF_SEARCH
    if gap(low) > 0:
        return None, "below_search_range"
    if gap(high) < 0:
        return None, "above_search_range"
    for _ in range(200):
        middle = (low + high) / 2
        if gap(middle) > 0:
            high = middle
        else:
            low = middle
        if high - low < 1e-10:
            break
    return (low + high) / 2, None


# ------------------------------------------------------------ hechos anuales
def _day(value: str) -> date:
    return date.fromisoformat(value)


def _years_before(anchor: str, years: int) -> date:
    day = _day(anchor)
    try:
        return day.replace(year=day.year - years)
    except ValueError:  # 29 de febrero
        return day.replace(year=day.year - years, day=28)


def _near(series: dict[str, float], day: date, tolerance: int = TOLERANCE_DAYS) -> float | None:
    close = [(abs((_day(end) - day).days), end) for end in series if abs((_day(end) - day).days) <= tolerance]
    return series[min(close)[1]] if close else None


def _instant(facts: dict, tags: list[str]) -> tuple[str | None, dict[str, float]]:
    for tag in tags:
        values = sec._extract_instant_values(facts, [tag])
        if values:
            return tag, dict(values)
    return None, {}


class _Facts:
    """Annual 10-K series by concept, read at one fiscal anchor."""

    def __init__(self, facts: dict):
        annual = {
            "revenue": sec.REVENUE_TAGS, "net_income": sec.NET_INCOME_TAGS, "ocf": sec.OCF_TAGS,
            "capex": sec.CAPEX_TAGS, "gross_profit": sec.GROSS_PROFIT_TAGS,
            "operating_income": sec.OPERATING_INCOME_TAGS, "depreciation": sec.DEPRECIATION_TAGS,
            "cost_of_revenue": COST_OF_REVENUE_TAGS, "interest": INTEREST_TAGS, "sbc": SBC_TAGS, "tax": TAX_TAGS,
            "pretax": PRETAX_TAGS, "impairment": IMPAIRMENT_TAGS, "debt_issuance": DEBT_ISSUANCE_TAGS,
            "dividends": DIVIDEND_TAGS, "buybacks": BUYBACK_TAGS,
        }
        self.series = {name: dict(sec._extract_annual_values(facts, tags)) for name, tags in annual.items()}
        instant = {
            "equity": sec.EQUITY_TAGS, "lt_debt": sec.LT_DEBT_TAGS, "cash": sec.CASH_TAGS,
            "debt_current": DEBT_CURRENT_TAGS, "lt_debt_current": LT_DEBT_CURRENT_TAGS,
            "short_borrowings": SHORT_BORROWING_TAGS, "short_investments": SHORT_INVESTMENT_TAGS,
            "goodwill": GOODWILL_TAGS, "assets": ASSETS_TAGS,
        }
        self.tags: dict[str, str | None] = {}
        for name, tags in instant.items():
            self.tags[name], self.series[name] = _instant(facts, tags)
        revenue, net_income = self.series["revenue"], self.series["net_income"]
        self.anchor = max(revenue) if revenue else max(net_income) if net_income else None

    def at(self, name: str, years_back: int = 0) -> float | None:
        if self.anchor is None:
            return None
        day = _years_before(self.anchor, years_back) if years_back else _day(self.anchor)
        value = _near(self.series[name], day)
        return None if value is None else float(value)

    def reason(self, name: str) -> str:
        return f"no_{name}" if not self.series[name] else f"stale_{name}"

    def gross_profit(self, years_back: int = 0) -> float | None:
        gross = self.at("gross_profit", years_back)
        if gross is not None:
            return gross
        revenue, cost = self.at("revenue", years_back), self.at("cost_of_revenue", years_back)
        return revenue - cost if revenue is not None and cost is not None else None

    def total_debt(self, years_back: int = 0) -> tuple[float | None, list[str], str | None]:
        """Long-term + current debt at the anchor; components never reported are listed, not zero-filled."""
        lt = self.at("lt_debt", years_back)
        if lt is None:
            return None, [], self.reason("lt_debt") if self.series["lt_debt"] else "no_debt_reported"
        missing: list[str] = []
        current = 0.0
        # us-gaap LongTermDebt already includes its current portion; only short borrowings remain.
        parts = ["short_borrowings"] if self.tags["lt_debt"] == "LongTermDebt" else (
            ["debt_current"] if self.series["debt_current"] else ["lt_debt_current", "short_borrowings"])
        for part in parts:
            value = self.at(part, years_back)
            if value is None:
                missing.append(part)
            else:
                current += value
        return lt + current, missing, None

    def liquidity(self, years_back: int = 0) -> tuple[float | None, list[str], str | None]:
        cash = self.at("cash", years_back)
        if cash is None:
            return None, [], self.reason("cash")
        investments = self.at("short_investments", years_back)
        return cash + (investments or 0.0), [] if investments is not None else ["short_investments"], None


def _cagr(first: float | None, last: float | None, years: int) -> float | None:
    if first is None or last is None or first <= 0 or last <= 0:
        return None
    return (last / first) ** (1 / years) - 1


def _growth_window(data: _Facts, name: str) -> tuple[float | None, int | None, float | None, str | None]:
    """CAGR over 10 years, else 5, and the dispersion of yearly growth in that window."""
    if data.at(name) is None:
        return None, None, None, data.reason(name)
    for years in GROWTH_YEARS:
        values = [data.at(name, back) for back in range(years, -1, -1)]
        if values[0] is None:
            continue
        cagr = _cagr(values[0], values[-1], years)
        if cagr is None:
            return None, years, None, "non_positive_start_or_end_value"
        growth = [right / left - 1 for left, right in zip(values, values[1:])
                  if left is not None and right is not None and left > 0]
        spread = float(_std(growth)) if len(growth) >= 3 else None
        return cagr, years, spread, None
    return None, None, None, f"fewer_than_{GROWTH_YEARS[-1] + 1}_annual_{name}_values"


def _std(values: list[float]) -> float:
    mean = sum(values) / len(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / (len(values) - 1))


def _ratio(numerator: float | None, denominator: float | None, *, positive: bool = True) -> float | None:
    if numerator is None or denominator is None or denominator == 0 or (positive and denominator < 0):
        return None
    return numerator / denominator


def shares_series(facts: dict) -> dict[str, float]:
    """Shares outstanding by date from every filing (cover pages included), latest filing per date."""
    best: dict[str, tuple[str, float]] = {}
    family = facts.get("facts", {}).get("us-gaap", {})
    for tag in sec.SHARES_TAGS:
        for entry in family.get(tag, {}).get("units", {}).get("shares", []):
            end, value, filed = entry.get("end"), entry.get("val"), str(entry.get("filed") or "")
            if end and value and value > 0 and (end not in best or filed >= best[end][0]):
                best[end] = (filed, float(value))
    return {end: value for end, (filed, value) in sorted(best.items())}


def share_basis(facts: dict) -> tuple[dict[str, float], str | None]:
    """Share counts by date and their source: recent outstanding shares, else the 10-K diluted average.

    Issuers with several share classes often report outstanding shares only per class, which
    companyfacts omits; the diluted average used for EPS is reported in total."""
    outstanding = shares_series(facts)
    annual = [dict(sec._extract_annual_values(facts, tags)) for tags in (sec.REVENUE_TAGS, sec.NET_INCOME_TAGS)]
    anchor = max(annual[0]) if annual[0] else max(annual[1]) if annual[1] else None
    if outstanding and (anchor is None or (_day(anchor) - _day(max(outstanding))).days <= SHARES_STALE_DAYS):
        return outstanding, "sec_outstanding"
    diluted = {end: float(value) for end, value in sec._extract_annual_values(facts, DILUTED_SHARES_TAGS,
                                                                             unit="shares") if value > 0}
    if diluted:
        return diluted, "sec_diluted_average"
    return {}, None


def verified_shares(shares: float | None, source: str | None, price: float | None,
                    yahoo_market_cap: float | None) -> tuple[float | None, str | None, bool]:
    """SEC shares in today's basis checked against Yahoo's market cap.

    Returns the shares to value the company with, their source and whether the SEC share basis
    is usable for history. Without SEC shares, Yahoo's market cap values the company. When SEC
    shares disagree beyond the tolerance, Yahoo's is used and the SEC share history is not."""
    if not price or not yahoo_market_cap or yahoo_market_cap <= 0:
        return shares, source, True
    if not shares:
        return yahoo_market_cap / price, "yahoo_no_sec_shares", True
    if abs(price * shares / yahoo_market_cap - 1) <= SHARE_CHECK_TOLERANCE:
        return shares, source, True
    return yahoo_market_cap / price, "yahoo_market_cap", False


@dataclass(frozen=True)
class MarketInputs:
    price: float | None = None
    price_date: str | None = None
    shares: float | None = None
    shares_date: str | None = None
    # sec_outstanding / sec_diluted_average / yahoo_market_cap (SEC shares did not match Yahoo) /
    # yahoo_no_sec_shares.
    shares_source: str | None = None
    # False when the SEC share basis disagrees with the price: share history is then unusable.
    share_history_ok: bool = True
    forward_eps: float | None = None
    # GABI's beta against SPY (ranking `beta_calc`), not Yahoo's.
    beta: float | None = None
    insiders_pct: float | None = None
    yahoo_fetched_at: str | None = None
    # Values of the ranking row (REFERENCE_KEYS) shown as secondary references, never mixed in.
    references: dict[str, float | None] = field(default_factory=dict)


# ----------------------------------------------------------------- evaluación
def _caveat(market: "MarketInputs", key: str) -> str | None:
    """Why a computed value may be unreliable; it is still shown, never hidden."""
    uncertain_classes = market.shares_source not in (None, "sec_outstanding")
    return "share_classes" if uncertain_classes and key in INSIDER_CAVEAT_KEYS else None


def _alternative(market: "MarketInputs", key: str) -> dict | None:
    if key not in ALTERNATIVES:
        return None
    metric, difference = ALTERNATIVES[key]
    value = market.references.get(metric)
    if value is None:
        return None
    source, period = METRIC_SOURCES[metric]
    return {"metric": metric, "value": float(value), "source": source, "period": period,
            "difference": difference, "explanation": DIFFERENCES[difference]}


def _verdict(rule: Rule, value, threshold: float | None, *, pe: float | None) -> str:
    if rule.comparison == "info":
        return "info"
    if rule.comparison == "<pe":
        return "missing" if pe is None else "pass" if value < pe else "fail"
    passed = {">=": value >= threshold, ">": value > threshold, "<=": value <= threshold,
              "<": value < threshold}[rule.comparison]
    return "pass" if passed else "fail"


def _insider_alarm(rows: list[dict], today: date) -> tuple[str, str | None, dict]:
    if not rows:
        return "missing", "no_insider_data", {}
    since = (today - timedelta(days=INSIDER_DAYS)).isoformat()
    sold: dict[str, float] = {}
    after: dict[str, tuple[str, float]] = {}
    for row in rows:
        day = str(row.get("transaction_date") or "")
        title = str(row.get("owner_title") or "").lower()
        officer = bool(row.get("is_officer")) or any(word in title for word in ("chief", "ceo", "cfo", "president"))
        if (day < since or day > today.isoformat() or row.get("transaction_code") != "S" or not officer
                or bool(row.get("is_10b5_1_plan"))):
            continue
        owner = str(row.get("owner_name") or "")
        sold[owner] = sold.get(owner, 0.0) + float(row.get("shares") or 0)
        held = row.get("shares_owned_after")
        if held is not None and (owner not in after or day >= after[owner][0]):
            after[owner] = (day, float(held))
    fractions = {owner: amount / (amount + after[owner][1]) for owner, amount in sold.items()
                 if owner in after and amount + after[owner][1] > 0}
    largest = max(fractions.values(), default=0.0)
    detail = {"sellers": len(sold), "largest_sold_fraction": largest if fractions else None}
    return ("active" if largest >= INSIDER_SOLD_FRACTION else "clear"), None, detail


def evaluate(facts: dict, market: MarketInputs, *, sector: str | None, thresholds: dict[str, float],
             edited: set[str], insider_rows: list[dict], today: date,
             split_factor_between: Callable[[str, str], float]) -> dict:
    """Evaluate every criterion, alarm and the reverse DCF from explicit inputs."""
    data = _Facts(facts)
    financial = sector in FINANCIAL_SECTORS
    anchor = data.anchor
    values: dict[str, float | None] = {}
    reasons: dict[str, str | None] = {}
    details: dict[str, dict] = {}

    def put(key: str, value, reason: str | None = None, **detail):
        values[key] = None if value is None else float(value)
        reasons[key] = None if value is not None else (reason or "missing_component")
        if detail:
            details[key] = detail

    revenue, net_income = data.at("revenue"), data.at("net_income")
    operating_income, depreciation = data.at("operating_income"), data.at("depreciation")
    ocf, capex = data.at("ocf"), data.at("capex")
    fcf = ocf - abs(capex) if ocf is not None and capex is not None else None

    cagr, years, spread, reason = _growth_window(data, "revenue")
    put("revenue_cagr", cagr, reason, years=years)
    put("revenue_growth_stability", spread, reason or ("too_few_years" if spread is None else None), years=years)
    cagr, years, _, reason = _growth_window(data, "ocf")
    put("cfo_cagr", cagr, reason, years=years)

    put("net_income", net_income, data.reason("net_income"))
    gross = data.gross_profit()
    put("gross_margin", _ratio(gross, revenue), "no_revenue" if revenue is None else "no_gross_profit")
    put("net_margin", _ratio(net_income, revenue), "no_revenue" if revenue is None else data.reason("net_income"))
    for key, now, then in (
            ("gross_margin_change", _ratio(gross, revenue),
             _ratio(data.gross_profit(TREND_YEARS), data.at("revenue", TREND_YEARS))),
            ("net_margin_change", _ratio(net_income, revenue),
             _ratio(data.at("net_income", TREND_YEARS), data.at("revenue", TREND_YEARS)))):
        put(key, now - then if now is not None and then is not None else None,
            "missing_component" if now is None else f"no_margin_{TREND_YEARS}_years_before",
            start=then, end=now, years=TREND_YEARS)

    debt, debt_missing, debt_reason = data.total_debt()
    liquid, liquid_missing, liquid_reason = data.liquidity()
    equity = data.at("equity")
    net_debt = debt - liquid if debt is not None and liquid is not None else None
    partial = debt_missing + liquid_missing
    put("net_debt", net_debt, debt_reason or liquid_reason, total_debt=debt, cash_and_investments=liquid,
        components_not_reported=partial)
    ebitda = operating_income + depreciation if operating_income is not None and depreciation is not None else None
    put("net_debt_to_ebitda", _ratio(net_debt, ebitda), "missing_component" if net_debt is None else "no_ebitda",
        ebitda=ebitda)

    tax, pretax = data.at("tax"), data.at("pretax")
    rate = _ratio(tax, pretax)
    rate = rate if rate is not None and 0 <= rate <= 1 else None
    invested = debt + equity - liquid if debt is not None and equity is not None and liquid is not None else None
    roic = None
    if operating_income is not None and rate is not None and invested is not None and invested > 0:
        roic = operating_income * (1 - rate) / invested
    put("roic", roic, ("no_operating_income" if operating_income is None else
                       "no_effective_tax_rate" if rate is None else
                       "missing_component" if invested is None else "non_positive_invested_capital"),
        tax_rate=rate, invested_capital=invested)

    interest = data.at("interest")
    if interest is not None and interest > 0 and operating_income is not None:
        put("interest_coverage", operating_income / interest)
    else:
        put("interest_coverage", None, "no_operating_income" if operating_income is None else
            "no_debt" if debt == 0 else data.reason("interest"))

    conversion = _ratio(ocf, net_income)
    ratios = [_ratio(data.at("ocf", back), data.at("net_income", back)) for back in range(TREND_YEARS)]
    history = [value for value in ratios if value is not None]
    put("cash_conversion", conversion,
        data.reason("ocf") if ocf is None else "non_positive_net_income",
        mean_5y=sum(history) / len(history) if history else None, years=len(history))
    put("cfo_margin", _ratio(ocf, revenue), "missing_component")
    put("fcf", fcf, data.reason("ocf") if ocf is None else data.reason("capex"))
    put("capex_to_revenue", _ratio(abs(capex) if capex is not None else None, revenue), "missing_component")

    shares, source = share_basis(facts)
    change, reason, share_detail = None, "no_shares", {}
    if shares and not market.share_history_ok:
        reason = "share_basis_mismatch"
    elif shares:
        latest = max(day for day in shares if day <= today.isoformat()) if any(
            day <= today.isoformat() for day in shares) else None
        if latest:
            target = _years_before(latest, SHARES_YEARS)
            old = min(shares, key=lambda day: abs((_day(day) - target).days))
            if abs((_day(old) - target).days) <= SHARES_TOLERANCE_DAYS:
                factor = split_factor_between(old, latest)
                change = shares[latest] / (shares[old] * factor) - 1
                share_detail = {"start": old, "end": latest, "split_factor": factor, "source": source}
            else:
                reason = f"no_shares_{SHARES_YEARS}_years_before"
    put("shares_change", change, reason, **share_detail)
    sbc = data.at("sbc")
    put("sbc_to_net_income", _ratio(sbc, net_income),
        data.reason("sbc") if sbc is None else "non_positive_net_income")

    market_cap = market.price * market.shares if market.price and market.shares else None
    market_reason = "no_price" if not market.price else "no_shares"
    put("market_cap", market_cap, market_reason, **({"shares_source": market.shares_source}
                                                     if market.shares_source else {}))
    enterprise = market_cap + net_debt if market_cap is not None and net_debt is not None else None
    put("enterprise_value", enterprise, market_reason if market_cap is None else "missing_component")
    pe = _ratio(market_cap, net_income) if net_income is not None and net_income > 0 else None
    put("pe", pe, market_reason if market_cap is None else "non_positive_net_income")
    forward = market.price / market.forward_eps if market.price and market.forward_eps and market.forward_eps > 0 \
        else None
    put("forward_pe", forward, "no_price" if not market.price else "no_forward_eps")
    for key, denominator, missing in (("ev_ebitda", ebitda, "no_ebitda"), ("ev_ebit", operating_income, "no_ebit"),
                                      ("ev_fcf", fcf, "no_fcf")):
        value = _ratio(enterprise, denominator) if denominator is not None and denominator > 0 else None
        put(key, value, "missing_component" if enterprise is None else missing)
    put("fcf_yield", _ratio(fcf, market_cap), market_reason if market_cap is None else "no_fcf")
    put("insiders_pct", market.insiders_pct, "not_captured")
    beta_class = None if market.beta is None else (
        "defensiva" if market.beta < 0.9 else "neutral" if market.beta <= 1.1 else "agresiva")
    put("beta", market.beta, "no_beta", **({"class": beta_class} if beta_class else {}))

    criteria = []
    for rule in RULES:
        value = values[rule.key]
        threshold = thresholds.get(rule.key)
        if financial and rule.key in FINANCIAL_NOT_APPLICABLE:
            verdict, reason = "not_applicable", "financial_sector"
        elif rule.key == "interest_coverage" and reasons[rule.key] == "no_debt":
            verdict, reason = "pass", "no_debt"
        elif value is None:
            verdict, reason = "missing", reasons[rule.key]
        else:
            verdict, reason = _verdict(rule, value, threshold, pe=values["pe"]), None
            if verdict == "missing":
                reason = reasons["pe"]
        criteria.append({
            "key": rule.key, "block": rule.block, "label": rule.label, "formula": rule.formula, "unit": rule.unit,
            "comparison": rule.comparison, "value": value, "threshold": threshold,
            "default_threshold": rule.default, "edited": rule.key in edited, "verdict": verdict, "reason": reason,
            "source": rule.source, "period": SOURCE_PERIODS[rule.source], "alternative": _alternative(market, rule.key),
            "reference": rule.reference, "explanation": EXPLANATIONS[rule.key],
            "caveat": _caveat(market, rule.key) if value is not None else None, "detail": details.get(rule.key, {}),
        })

    alarms = _alarms(data, values, market, thresholds, insider_rows, today, financial, fcf)
    dcf = _dcf(market, fcf, values, thresholds, edited, financial)
    passed = sum(item["verdict"] == "pass" for item in criteria)
    failed = sum(item["verdict"] == "fail" for item in criteria)
    return {
        "fiscal_year_end": anchor,
        "financial_sector": financial,
        "summary": {"passed": passed, "failed": failed, "evaluated": passed + failed,
                    "missing": sum(item["verdict"] == "missing" for item in criteria),
                    "score": passed / (passed + failed) if passed + failed else None,
                    "alarms_active": sum(item["status"] == "active" for item in alarms),
                    "alarms_evaluated": sum(item["status"] in {"active", "clear"} for item in alarms)},
        "criteria": criteria,
        "alarms": alarms,
        "dcf": dcf,
        "qualitative": [{"key": key, "label": label, "hint": hint} for key, label, hint in QUALITATIVE],
    }


def _alarm(key: str, label: str, check: str, status: str, reason: str | None = None, *,
           caveat: str | None = None, **detail) -> dict:
    return {"key": key, "label": label, "check": check, "explanation": ALARM_EXPLANATIONS[key], "status": status,
            "reason": reason, "caveat": caveat, "detail": detail}


def _alarms(data: _Facts, values: dict, market: MarketInputs, thresholds: dict, insider_rows: list[dict],
            today: date, financial: bool, fcf: float | None) -> list[dict]:
    back = ALARM_YEARS
    rows = []

    def not_applicable(key, label, check):
        return _alarm(key, label, check, "not_applicable", "financial_sector")

    label, check = ("Beneficio neto crece pero el CFO se estanca o queda por debajo",
                    "Cuentas por cobrar e inventario en el working capital")
    ni_now, ni_then, cfo_now, cfo_then = (data.at("net_income"), data.at("net_income", back), data.at("ocf"),
                                          data.at("ocf", back))
    below = [_ratio(data.at("ocf", year), data.at("net_income", year)) for year in range(back)]
    if financial:
        rows.append(not_applicable("earnings_outpace_cfo", label, check))
    elif (ni_now is None or ni_then is None or cfo_now is None or cfo_then is None
          or ni_then <= 0 or cfo_then <= 0):
        rows.append(_alarm("earnings_outpace_cfo", label, check, "missing", "missing_component"))
    else:
        outpaces = ni_now / ni_then > cfo_now / cfo_then
        weak_years = sum(value is not None and value < 1 for value in below)
        rows.append(_alarm("earnings_outpace_cfo", label, check,
                           "active" if outpaces and weak_years >= 2 else "clear",
                           net_income_growth=ni_now / ni_then - 1, cfo_growth=cfo_now / cfo_then - 1,
                           years_cfo_below_net_income=weak_years, years=back))

    label, check = "Deuda subiendo con un CFO débil", "Flujo de caja de financiación frente al operativo"
    debt_now, debt_then = data.at("lt_debt"), data.at("lt_debt", back)
    if financial:
        rows.append(not_applicable("debt_up_weak_cfo", label, check))
    elif debt_now is None or debt_then is None or cfo_now is None or cfo_then is None or ni_now is None:
        rows.append(_alarm("debt_up_weak_cfo", label, check, "missing", "missing_component"))
    else:
        rising = debt_now > debt_then * (1 + DEBT_GROWTH_ALARM)
        weak = cfo_now < cfo_then or (ni_now > 0 and cfo_now / ni_now < 1)
        rows.append(_alarm("debt_up_weak_cfo", label, check, "active" if rising and weak else "clear",
                           long_term_debt_growth=debt_now / debt_then - 1 if debt_then else None, years=back))

    label, check = "Recompras financiadas con deuda", "Emisión de deuda ≈ importe de recompras"
    buybacks, issuance = data.at("buybacks"), data.at("debt_issuance")
    if buybacks is None or abs(buybacks) == 0:
        rows.append(_alarm("buybacks_with_debt", label, check, "clear" if data.series["buybacks"] else "missing",
                           None if data.series["buybacks"] else "no_buybacks_reported"))
    elif issuance is None or fcf is None:
        rows.append(_alarm("buybacks_with_debt", label, check, "missing",
                           "no_fcf" if fcf is None else data.reason("debt_issuance")))
    else:
        active = abs(buybacks) > fcf and abs(issuance) >= 0.5 * abs(buybacks)
        rows.append(_alarm("buybacks_with_debt", label, check, "active" if active else "clear",
                           buybacks=abs(buybacks), debt_issuance=abs(issuance), fcf=fcf))

    label, check = "Dividendos financiados con deuda", "Dividendos > FCF y deuda creciendo"
    dividends, debt_prior = data.at("dividends"), data.at("lt_debt", 1)
    if dividends is None or fcf is None or debt_now is None or debt_prior is None:
        rows.append(_alarm("dividends_with_debt", label, check, "missing",
                           data.reason("dividends") if dividends is None else "missing_component"))
    else:
        active = abs(dividends) > fcf and debt_now > debt_prior
        rows.append(_alarm("dividends_with_debt", label, check, "active" if active else "clear",
                           dividends=abs(dividends), fcf=fcf))

    label, check = "Mucho goodwill o deterioros repetidos", "Balance › Goodwill; deterioros en resultados"
    goodwill, assets = data.at("goodwill"), data.at("assets")
    impairments = [data.at("impairment", year) for year in range(TREND_YEARS)]
    if goodwill is None or not assets:
        rows.append(_alarm("goodwill", label, check, "missing",
                           data.reason("goodwill") if goodwill is None else data.reason("assets")))
    else:
        repeated = sum(value is not None and value > 0 for value in impairments)
        share = goodwill / assets
        rows.append(_alarm("goodwill", label, check,
                           "active" if share >= GOODWILL_ASSETS_ALARM or repeated >= 2 else "clear",
                           goodwill_to_assets=share, impairment_years=repeated))

    label, check = "Dilución continua (ampliaciones o SBC alto)", "Nº de acciones en 5 años y SBC"
    change, sbc_ratio = values["shares_change"], values["sbc_to_net_income"]
    if change is None and sbc_ratio is None:
        rows.append(_alarm("dilution", label, check, "missing", "missing_component"))
    else:
        active = (change is not None and change > 0) or (
            sbc_ratio is not None and sbc_ratio >= thresholds["sbc_to_net_income"])
        rows.append(_alarm("dilution", label, check, "active" if active else "clear",
                           shares_change=change, sbc_to_net_income=sbc_ratio))

    status, reason, detail = _insider_alarm(insider_rows, today)
    rows.append(_alarm("executives_selling", "Directivos vendiendo de forma masiva",
                       "Form 4: ventas en mercado (sin plan 10b5-1) ≥ 20 % de su posición en 6 meses",
                       status, reason, **detail))

    label, check = "CEO sin acciones, solo sueldo y bonus", "% en manos de directivos"
    if market.insiders_pct is None:
        rows.append(_alarm("no_skin_in_the_game", label, check, "missing", "not_captured"))
    else:
        rows.append(_alarm("no_skin_in_the_game", label, check,
                           "active" if market.insiders_pct < NO_SKIN_FRACTION else "clear",
                           caveat=_caveat(market, "no_skin_in_the_game"), insiders_pct=market.insiders_pct))

    rows.append(_alarm("blames_external_factors", "La directiva siempre culpa a factores externos",
                       "Conference calls trimestrales", "manual"))
    rows.append(_alarm("adjusted_ebitda", "Uso de EBITDA «ajustado» a medida", "Compara con EBIT (métrica GAAP)",
                       "info", "gaap_ebitda"))
    rows.append(_alarm("market_share_loss", "Pierde cuota de mercado aunque «tiene foso»",
                       "Cuota de mercado frente a competidores", "manual"))

    label, check = "CAPEX disparado sin aumento posterior del CFO", "CAPEX / ventas y evolución del CFO"
    revenue_now, revenue_then = data.at("revenue"), data.at("revenue", back)
    capex_now, capex_then = data.at("capex"), data.at("capex", back)
    intensity_now = _ratio(abs(capex_now) if capex_now is not None else None, revenue_now)
    intensity_then = _ratio(abs(capex_then) if capex_then is not None else None, revenue_then)
    margin_now, margin_then = _ratio(cfo_now, revenue_now), _ratio(cfo_then, revenue_then)
    if financial:
        rows.append(not_applicable("capex_spike", label, check))
    elif intensity_now is None or intensity_then is None or margin_now is None or margin_then is None:
        rows.append(_alarm("capex_spike", label, check, "missing", "missing_component"))
    else:
        active = intensity_now - intensity_then >= CAPEX_SPIKE_POINTS and margin_now <= margin_then
        rows.append(_alarm("capex_spike", label, check, "active" if active else "clear",
                           capex_to_revenue_change=intensity_now - intensity_then,
                           cfo_margin_change=margin_now - margin_then, years=back))
    return rows


def _dcf(market: MarketInputs, fcf: float | None, values: dict, thresholds: dict, edited: set[str],
         financial: bool) -> dict:
    parameters = {key: thresholds[key] for key in DCF_DEFAULTS}
    result = {**parameters, "edited": sorted(key for key in DCF_DEFAULTS if key in edited), "fcf": fcf,
              "shares": market.shares, "price": market.price, "implied_growth": None,
              "historical_cfo_cagr": values["cfo_cagr"], "value_per_share_at_history": None,
              "verdict": "missing", "reason": None}
    reference = values["cfo_cagr"]
    if financial:
        return result | {"verdict": "not_applicable", "reason": "financial_sector"}
    if not market.price or not market.shares:
        return result | {"reason": "no_price" if not market.price else "no_shares"}
    if fcf is None or fcf <= 0:
        return result | {"reason": "no_fcf" if fcf is None else "non_positive_fcf"}
    options = {"discount_rate": parameters["dcf_discount_rate"],
               "terminal_growth": parameters["dcf_terminal_growth"], "years": int(parameters["dcf_years"])}
    growth, reason = implied_growth(market.price, fcf, market.shares, **options)
    if reference is not None:
        result["value_per_share_at_history"] = dcf_value_per_share(fcf, market.shares, reference, **options)
    if growth is None:
        verdict = "discard" if reason == "above_search_range" else "reasonable"
        return result | {"verdict": verdict, "reason": reason}
    if growth >= parameters["dcf_max_implied_growth"]:
        verdict = "discard"
    elif reference is None:
        verdict, reason = "missing", "no_historical_growth"
    else:
        verdict = "reasonable" if growth <= reference else "demanding"
    return result | {"implied_growth": growth, "verdict": verdict, "reason": reason}


# ------------------------------------------- múltiplos frente a historia y sector
MULTIPLE_KEYS = ("pe", "ev_ebitda", "ev_ebit", "ev_fcf")
MULTIPLE_YEARS = 5
MIN_HISTORY_VALUES = 3
MIN_SECTOR_PEERS = 5
EV_MULTIPLES = frozenset({"ev_ebitda", "ev_ebit", "ev_fcf"})
# Annual figures only come from these forms; share counts also come from 10-Q cover pages.
ANNUAL_FORMS = ("10-K", "10-K/A")
# Tags a peer needs for its current multiples; a bounded read instead of its whole history.
MULTIPLE_TAGS = list(dict.fromkeys(
    sec.REVENUE_TAGS + sec.NET_INCOME_TAGS + sec.OCF_TAGS + sec.CAPEX_TAGS + sec.OPERATING_INCOME_TAGS
    + sec.DEPRECIATION_TAGS + sec.LT_DEBT_TAGS + sec.CASH_TAGS + DEBT_CURRENT_TAGS + LT_DEBT_CURRENT_TAGS
    + SHORT_BORROWING_TAGS + SHORT_INVESTMENT_TAGS + sec.SHARES_TAGS + DILUTED_SHARES_TAGS))


def _multiples(data: _Facts, market_cap: float | None, years_back: int = 0) -> dict[str, float | None]:
    """PER and EV multiples of one fiscal year, with the same formulas as the checklist criteria."""
    empty: dict[str, float | None] = dict.fromkeys(MULTIPLE_KEYS)
    if market_cap is None or market_cap <= 0:
        return empty
    net_income = data.at("net_income", years_back)
    operating_income, depreciation = data.at("operating_income", years_back), data.at("depreciation", years_back)
    ocf, capex = data.at("ocf", years_back), data.at("capex", years_back)
    debt, liquid = data.total_debt(years_back)[0], data.liquidity(years_back)[0]
    enterprise = market_cap + debt - liquid if debt is not None and liquid is not None else None
    ebitda = operating_income + depreciation if operating_income is not None and depreciation is not None else None
    fcf = ocf - abs(capex) if ocf is not None and capex is not None else None
    result = dict(empty)
    result["pe"] = _ratio(market_cap, net_income) if net_income is not None and net_income > 0 else None
    for key, denominator in (("ev_ebitda", ebitda), ("ev_ebit", operating_income), ("ev_fcf", fcf)):
        if enterprise is not None and denominator is not None and denominator > 0:
            result[key] = enterprise / denominator
    return result


def _median(values: list[float]) -> float | None:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if not ordered:
        return None
    return ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2


def _year_end(data: _Facts, years_back: int) -> str | None:
    """Actual fiscal year end reported near the anchor minus ``years_back`` years."""
    if data.anchor is None:
        return None
    series = data.series["revenue"] or data.series["net_income"]
    target = _years_before(data.anchor, years_back) if years_back else _day(data.anchor)
    close = [(abs((_day(end) - target).days), end) for end in series
             if abs((_day(end) - target).days) <= TOLERANCE_DAYS]
    return min(close)[1] if close else None


def current_multiples(facts: dict, price: float | None, shares: float | None) -> dict[str, float | None]:
    """Latest fiscal year multiples at today's price, for sector peers."""
    return _multiples(_Facts(facts), price * shares if price and shares else None)


def multiples_history(facts: dict, *, close_on: Callable[[str], float | None],
                      split_factor_after: Callable[[str], float], financial: bool,
                      share_history_ok: bool = True) -> dict:
    """Own multiples over the last fiscal years, each at its year-end close and shares.

    Prices are in today's split basis, so shares are moved to it with the splits after their date.
    Figures of each year are those known today (later restatements included)."""
    data, (shares, _) = _Facts(facts), share_basis(facts)
    years, multiples = [], []
    for back in range(MULTIPLE_YEARS if share_history_ok else 0):
        end = _year_end(data, back)
        if end is None:
            continue
        near = [(abs((_day(day) - _day(end)).days), day) for day in shares
                if abs((_day(day) - _day(end)).days) <= SHARES_TOLERANCE_DAYS]
        price = close_on(end)
        share_day = min(near)[1] if near else None
        market_cap = (price * shares[share_day] * split_factor_after(share_day)
                      if price and price > 0 and share_day else None)
        multiples.append(_multiples(data, market_cap, back))
        years.append({"fiscal_year_end": end, "price": price, "shares_date": share_day, "market_cap": market_cap,
                      **multiples[-1]})
    summary: dict[str, dict] = {}
    for key in MULTIPLE_KEYS:
        values = [value for row in multiples if (value := row[key]) is not None]
        if financial and key in EV_MULTIPLES:
            summary[key] = {"median": None, "count": 0, "reason": "financial_sector"}
        elif not share_history_ok:
            summary[key] = {"median": None, "count": 0, "reason": "share_basis_mismatch"}
        elif len(values) < MIN_HISTORY_VALUES:
            summary[key] = {"median": None, "count": len(values), "reason": f"fewer_than_{MIN_HISTORY_VALUES}_years"}
        else:
            summary[key] = {"median": _median(values), "count": len(values), "reason": None}
    return {"years": MULTIPLE_YEARS, "by_year": years, "median": summary}


def sector_medians(peers: dict[str, dict[str, float | None]], *, financial: bool) -> dict:
    """Median of each multiple across sector peers with a value; too few peers leave it absent."""
    result: dict[str, dict] = {}
    for key in MULTIPLE_KEYS:
        values = [float(value) for row in peers.values() if (value := row.get(key)) is not None]
        if financial and key in EV_MULTIPLES:
            result[key] = {"median": None, "count": 0, "reason": "financial_sector"}
        elif len(values) < MIN_SECTOR_PEERS:
            result[key] = {"median": None, "count": len(values), "reason": f"fewer_than_{MIN_SECTOR_PEERS}_peers"}
        else:
            result[key] = {"median": _median(values), "count": len(values), "reason": None}
    return result
