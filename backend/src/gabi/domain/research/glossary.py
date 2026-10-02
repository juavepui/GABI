"""Plain-language definitions of the technical terms GABI shows. One source for the ⓘ hints and Aprender."""

# Terms not covered by the metric help (domain/market/metric_info.py): research statistics and data concepts.
TERMS: dict[str, tuple[str, str]] = {
    "psr": ("PSR (Probabilistic Sharpe Ratio)",
            "Probabilidad de que el Sharpe verdadero supere un umbral (aquí, cero), teniendo en cuenta cuántos "
            "periodos hay y si los retornos tienen colas gordas o asimetría. Un Sharpe alto con pocos datos puede "
            "tener un PSR modesto."),
    "dsr": ("DSR (Deflated Sharpe Ratio)",
            "El PSR corregido por el número de variantes que se probaron. Cuantas más configuraciones se ensayan, "
            "más fácil es que una salga bien por suerte; el DSR descuenta esa búsqueda."),
    "pbo": ("PBO (Probabilidad de sobreajuste)",
            "Con qué frecuencia la configuración que mejor sale en una mitad de los datos queda por debajo de la "
            "mediana en la otra mitad. Un PBO alto indica que elegir «la mejor» es sobre todo ruido."),
    "block_bootstrap": ("Bootstrap por bloques",
                        "Remuestreo de la serie de retornos en bloques consecutivos para estimar la incertidumbre "
                        "de un resultado sin romper la dependencia entre periodos cercanos."),
    "rank_ic": ("Rank IC (coeficiente de información)",
                "Correlación de rangos entre el score de una fecha y el retorno posterior de cada empresa. Positivo "
                "y estable = el score ordena bien; cerca de cero = no ordena."),
    "hhi": ("HHI (índice de concentración)",
            "Suma de los pesos al cuadrado de la cartera. Cuanto más alto, más concentrado está el capital: 20 "
            "posiciones con pesos muy desiguales pueden comportarse como muchas menos."),
    "point_in_time": ("Point-in-time",
                      "Usar solo la información que existía en una fecha pasada: la lista del índice de ese día, los "
                      "informes ya presentados y los precios hasta entonces. Evita mirar al futuro sin darse "
                      "cuenta."),
    "cik": ("CIK",
            "Identificador que la SEC asigna a cada empresa. Permite seguirla aunque cambie de nombre o de ticker; "
            "sin CIK no se pueden leer sus informes oficiales."),
    "out_of_sample": ("Fuera de muestra (out-of-sample)",
                      "Datos que no se usaron para elegir la configuración. Solo un resultado fuera de muestra, o el "
                      "seguimiento real hacia delante, puede confirmar lo que un backtest sugiere."),
    "live_forward": ("Live forward",
                     "Seguimiento real hacia delante: la estrategia se registra antes de conocer el resultado y se "
                     "evalúa con datos que aún no existían."),
    "holdout": ("Reserva (holdout)",
                "Periodo de datos guardado sin mirar para una única prueba final. Consultarlo antes de tiempo lo "
                "invalida, por eso GABI lo protege en el backend."),
    "percentile": ("Percentil sectorial",
                   "Posición de una empresa frente a las de su mismo sector, de 0 a 100. 100 es la mejor del "
                   "sector en esa métrica, ya teniendo en cuenta si conviene un valor alto o bajo."),
}

# Metric help reused as terms (same text as the tooltips of every table).
METRIC_TERMS = ("composite_score", "confidence", "sharpe_ratio", "sortino_ratio", "max_drawdown", "volatility")


def glossary(metric_info: dict[str, dict[str, str]]) -> list[dict[str, str]]:
    entries = [{"key": key, "term": term, "definition": definition} for key, (term, definition) in TERMS.items()]
    entries += [{"key": key, "term": metric_info[key]["label"], "definition": metric_info[key]["help"]}
                for key in METRIC_TERMS if key in metric_info]
    return sorted(entries, key=lambda entry: entry["term"].lower())
