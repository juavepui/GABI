"""How each cached FRED series is published and how to read it (#195).

`fred.SERIES` keeps the synchronized metadata unchanged; this adds what the Macro panel and the Home
strip need: publication frequency, what each value aggregates, revised help texts and the series of
the Home strip. Nothing here changes a stored value or the score.
"""

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


def macro_metadata(series: dict[str, dict]) -> dict[str, dict]:
    """The synchronized metadata with frequency, aggregation, Home flag and the revised help."""
    return {key: dict(meta) | {"home": False} | PRESENTATION[key] for key, meta in series.items()}
