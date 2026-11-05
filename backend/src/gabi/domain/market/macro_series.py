"""How each cached FRED series is published and how to read it (#195).

`fred.SERIES` keeps the synchronized metadata unchanged; this adds what the Macro panel and the Home
strip need: publication frequency, what each value aggregates, revised help texts and the series of
the Home strip. Nothing here changes a stored value or the score.

`fred.SERIES` is pinned to the captured legacy module (test_fred_migration), so the series added later
(#309) live in `NEW_SERIES` and `synchronized_series()` joins both for the refresh and the panel.
"""

from types import MappingProxyType

from gabi.domain.market import fred
from gabi.domain.market.macro_labels import BLOCKS

# Same fields as fred.SERIES. Free FRED series, refreshed with the others.
NEW_SERIES: dict[str, dict] = {
    "NFCI": {
        "label": "Condiciones financieras (NFCI)", "unit": "índice", "units_param": "lin",
        "help": "Índice semanal de la Reserva Federal de Chicago que resume más de 100 datos de crédito, bolsa y "
                "bancos. Vale 0 en condiciones medias: por debajo de 0, pedir dinero prestado es más fácil de lo "
                "normal (condiciones holgadas); por encima, más difícil (tensas).",
    },
    "UNRATE": {
        "label": "Tasa de paro", "unit": "%", "units_param": "lin",
        "help": "Porcentaje de la población activa de EE. UU. que busca trabajo y no lo encuentra. Se publica "
                "cada mes; una subida rápida desde mínimos ha acompañado a las recesiones.",
    },
    "ICSA": {
        "label": "Nuevas peticiones de paro", "unit": "personas", "units_param": "lin",
        "help": "Personas que piden el subsidio de paro por primera vez cada semana en EE. UU. Es de los datos "
                "de empleo que antes llegan: si suben varias semanas seguidas, el mercado laboral se enfría. "
                "Una sola semana dice poco: hay festivos, temporales y ajustes por estación.",
    },
    "VIXCLS": {
        "label": "Nerviosismo de la bolsa (VIX)", "unit": "índice", "units_param": "lin",
        "help": "Cuánto esperan los inversores que se mueva el S&P 500 en el próximo mes, sacado del precio de las "
                "opciones. Por debajo de 20 es lo habitual en calma; por encima de 30, miedo. Sube de golpe en las "
                "caídas fuertes y baja despacio. Describe el ánimo de hoy; no dice hacia dónde irá la bolsa.",
    },
    "T10YIE": {
        "label": "Inflación esperada a 10 años", "unit": "%", "units_param": "lin",
        "help": "La inflación media que espera el mercado para los próximos 10 años, sacada de la diferencia "
                "entre el bono normal y el protegido contra la inflación (TIPS). Si se aleja mucho del 2 % "
                "que busca la Fed, el mercado duda de que la inflación vaya a estar controlada.",
    },
}

PRESENTATION: dict[str, dict] = {
    "DGS10": {"frequency": "daily", "aggregation": "end_of_period", "home": True},
    "DFII10": {"frequency": "daily", "aggregation": "end_of_period", "home": True},
    "FEDFUNDS": {
        "frequency": "monthly", "aggregation": "average",
        "help": "Tipo efectivo de los fondos federales, media del mes. Su subida encarece el crédito para empresas "
                "y consumidores. Un recorte no es alcista por sí mismo: depende de si responde a una inflación "
                "contenida o a una recesión, y en recesiones la bolsa ha caído pese a los recortes. Al ser una "
                "media mensual, el cambio a 3 meses puede no ser un múltiplo de los saltos de 0,25 p. p. con los "
                "que se mueve la Fed.",
    },
    "T10Y2Y": {
        "frequency": "daily", "aggregation": "end_of_period", "home": True,
        "help": "Diferencia entre el tipo a 10 años y a 2 años. Cuando es negativa (curva invertida), ha precedido "
                "a las recesiones de EE.UU., con un adelanto muy variable (de meses a más de dos años) y alguna "
                "falsa alarma; no indica cuándo.",
    },
    "CPIAUCSL": {"frequency": "monthly", "aggregation": "year_over_year"},
    "DTWEXBGS": {"frequency": "daily", "aggregation": "end_of_period"},
    "BAMLH0A0HYM2": {"frequency": "daily", "aggregation": "end_of_period", "home": True},
    "WALCL": {"frequency": "weekly", "aggregation": "wednesday_level"},
    "SAHMREALTIME": {
        "frequency": "monthly", "aggregation": "three_month_average",
        "help": "Media de 3 meses del paro menos su mínimo de los 12 meses anteriores. Por encima de 0,5 ha "
                "coincidido con el inicio de las recesiones de EE.UU.; señala cuando la recesión ya ha empezado, "
                "no la anticipa.",
    },
}


PRESENTATION |= {
    "NFCI": {"frequency": "weekly", "aggregation": "end_of_period"},
    "UNRATE": {"frequency": "monthly", "aggregation": "end_of_period"},
    "ICSA": {"frequency": "weekly", "aggregation": "end_of_period"},
    "T10YIE": {"frequency": "daily", "aggregation": "end_of_period"},
    "VIXCLS": {"frequency": "daily", "aggregation": "end_of_period"},  # #308
}

BLOCK = {series_id: block for block, (_, members) in BLOCKS.items() for series_id in members}


def synchronized_series() -> MappingProxyType:
    """Every FRED series GABI refreshes and shows: the captured ones and those added in #309."""
    return MappingProxyType({**fred.SERIES, **{key: MappingProxyType(value) for key, value in NEW_SERIES.items()}})


def macro_metadata(series: dict[str, dict]) -> dict[str, dict]:
    """The synchronized metadata with frequency, aggregation, Home flag, block and the revised help."""
    return {key: dict(meta) | {"home": False} | PRESENTATION[key] | {"block": BLOCK[key]}
            for key, meta in series.items()}
