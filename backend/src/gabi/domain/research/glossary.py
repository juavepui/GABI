"""Plain-language definitions of the technical terms GABI shows. One source for the ⓘ hints and Aprender."""

# Terms not covered by the metric help (domain/market/metric_info.py): research statistics and data concepts.
TERMS: dict[str, tuple[str, str]] = {
    "psr": ("PSR (Probabilistic Sharpe Ratio)",
            "Probabilidad de que la estrategia tenga de verdad una rentabilidad por riesgo (Sharpe) "
            "positiva, y no solo por suerte. Tiene en cuenta cuántos datos hay y si hubo sustos "
            "extremos: un Sharpe alto con pocos años de datos puede dar un PSR modesto."),
    "dsr": ("DSR (Deflated Sharpe Ratio)",
            "Como el PSR, pero descontando cuántas variantes se probaron antes de elegir esta. Si "
            "pruebas 100 configuraciones, alguna saldrá bien por casualidad; el DSR resta esa ventaja "
            "de haber buscado mucho."),
    "pbo": ("PBO (Probabilidad de sobreajuste)",
            "Probabilidad de que «la mejor» configuración lo sea solo por casualidad. Se elige la mejor "
            "con la mitad de los datos y se mira cómo queda en la otra mitad: si a menudo cae por "
            "debajo de la media, el PBO es alto y elegir la mejor es sobre todo ruido."),
    "block_bootstrap": ("Bootstrap por bloques",
                        "Forma de medir la incertidumbre de un resultado: se rehace la historia muchas veces "
                        "mezclando trozos de meses seguidos (para no romper rachas) y se mira cuánto cambia el "
                        "resultado. Da un rango en lugar de un único número."),
    "rank_ic": ("Rank IC (coeficiente de información)",
                "Mide si una puntuación ordena bien: compara, en cada fecha, el orden de las empresas por "
                "puntuación con el orden por lo que subieron después. De −1 a 1; por encima de 0 = las "
                "mejor puntuadas tendieron a subir más; cerca de 0 = no ordena. En bolsa, 0,05 ya se "
                "considera interesante."),
    "hhi": ("HHI (índice de concentración)",
            "Mide lo concentrada que está una cartera (suma de los pesos al cuadrado). Cuanto más alto, "
            "más depende de unas pocas empresas: 20 posiciones con pesos muy desiguales pueden "
            "comportarse como muchas menos."),
    "point_in_time": ("Point-in-time",
                      "Usar solo lo que se sabía en cada fecha pasada: las empresas que estaban entonces en el "
                      "índice, los informes ya publicados y los precios hasta ese día. Evita «mirar el futuro» "
                      "sin darse cuenta, que hace que un backtest parezca mejor de lo que fue."),
    "cik": ("CIK",
            "Número que la SEC asigna a cada empresa. Permite seguirla aunque cambie de nombre o de "
            "símbolo; sin él no se pueden leer sus informes oficiales."),
    "out_of_sample": ("Fuera de muestra (out-of-sample)",
                      "Datos que no se usaron para diseñar ni elegir la estrategia. Solo un buen resultado aquí, "
                      "o en el seguimiento en vivo, puede confirmar lo que sugiere un backtest."),
    "live_forward": ("Seguimiento en vivo (live forward)",
                     "La prueba más honesta: se apunta la estrategia antes de conocer el resultado y se comprueba "
                     "después con datos que todavía no existían, así que no puede ajustarse a posteriori."),
    "holdout": ("Reserva (holdout)",
                "Un periodo de datos guardado sin mirar para una única prueba final. Si se consulta antes "
                "de tiempo, deja de servir; por eso GABI lo bloquea en el servidor."),
    "icir": ("ICIR (estabilidad del IC)",
             "El IC medio dividido entre lo mucho que varía de un periodo a otro. Un IC pequeño pero muy "
             "constante puede valer más que uno grande que va y viene. Por encima de 0,5 se suele "
             "considerar estable."),
    "holm": ("Corrección de Holm (p Holm)",
             "Cuantas más métricas se prueban, más fácil es que alguna salga bien por casualidad. La "
             "corrección de Holm endurece el listón para compensarlo. Un «p Holm» por debajo de 0,05 "
             "significa que el resultado difícilmente se explica por suerte, aun contando todas las "
             "pruebas hechas."),
    "quintile_spread": ("Diferencia Q5−Q1",
                        "Se ordenan las empresas por una métrica y se parten en cinco grupos iguales "
                        "(quintiles). Es la diferencia de rentabilidad entre el mejor grupo (Q5) y el peor "
                        "(Q1). Positiva = las mejor puntuadas rindieron más."),
    "backtest": ("Backtest (prueba con datos del pasado)",
                 "Simular cómo habría ido una estrategia si se hubiera aplicado en el pasado. Es útil "
                 "para descartar ideas, pero fácil de engañar: si se prueban muchas variantes, alguna "
                 "saldrá bien por casualidad."),
    "in_sample": ("Dentro de muestra (in-sample)",
                  "Los datos con los que se diseñó o eligió la estrategia. Un buen resultado aquí es "
                  "esperable y no demuestra nada por sí solo; hay que confirmarlo fuera de muestra."),
    "rebalance": ("Rebalanceo",
                  "Revisar la cartera cada cierto tiempo (cada mes, trimestre…) para volver a la "
                  "selección y los pesos que marca la regla. Cada rebalanceo implica compras, ventas y "
                  "comisiones."),
    "preregistration": ("Preregistro",
                        "Dejar escritas las reglas de una prueba (qué se mide, cuándo y qué contará como "
                        "éxito) antes de ver el resultado. Así no se pueden cambiar las reglas a "
                        "posteriori para que la estrategia parezca mejor."),
    "seal": ("Sello (cadena de hashes)",
             "Una huella digital de cada registro que incluye la del registro anterior. Si alguien "
             "cambiara un dato del pasado, la cadena dejaría de cuadrar; por eso «íntegra» significa "
             "que nada se ha tocado."),
    "commit": ("Commit (versión del código)",
               "Identificador de la versión exacta del programa con la que se hizo un cálculo. Permite "
               "repetirlo después y comprobar que da lo mismo."),
    "block_coverage": ("Cobertura por apartado",
                       "Qué parte de todas las empresas tiene todos los datos de un apartado de la puntuación "
                       "(valoración, calidad, momentum o riesgo). Habla del ranking entero, no de una empresa: si "
                       "en un apartado faltan muchos datos, comparar empresas por ese apartado es menos fiable."),
    "percentile": ("Percentil sectorial",
                   "Puesto de una empresa frente a las de su mismo sector, en una escala de 0 a 100. Un 80 quiere "
                   "decir que sale mejor que el 80 % de su sector en esa métrica (ya teniendo en cuenta si "
                   "conviene un número alto o bajo). 100 es la mejor del sector."),
    "spearman": ("Acuerdo de orden (Spearman)",
                 "Mide si dos listas ordenan las empresas igual. De −1 a 1: 1 = exactamente el mismo orden; "
                 "0 = el orden de una no dice nada del de la otra. Solo mira los puestos, no los números: dos "
                 "listas pueden tener un 0,9 aunque sus puntuaciones sean distintas."),
    "form_8k": ("8-K (hecho relevante)",
                "Aviso que una empresa de EE. UU. envía a la SEC en pocos días cuando pasa algo importante: "
                "resultados, una compra, un cambio de directivos, de auditor… Es la forma oficial de "
                "contarlo a todos los inversores a la vez. Un 8-K/A corrige o completa uno anterior."),
    "item_8k": ("Item de un 8-K",
                "Código con el que la empresa marca de qué trata su 8-K, por ejemplo 2.02 = resultados o "
                "5.02 = cambio de directivos. Lo pone la propia empresa; GABI solo lo traduce con una tabla "
                "fija, sin leer ni interpretar el texto. Un código que no está en la tabla se muestra «sin "
                "clasificar»."),
    "accession": ("Número de registro (accession)",
                  "Identificador único que la SEC da a cada documento presentado, como 0000320193-25-000071. "
                  "Sirve para encontrar exactamente ese documento en la web de la SEC."),
    "restatement": ("Reexpresión de cuentas",
                    "Cuando una empresa reconoce que unas cuentas ya publicadas tenían errores y no se deben "
                    "usar (Item 4.02 del 8-K). Es una señal seria: los números con que se analizó la empresa "
                    "pueden estar mal."),
    "ttm_vs_annual": ("Últimos 12 meses frente a ejercicio anual",
                      "Yahoo suma los cuatro últimos trimestres (últimos 12 meses, TTM) y se actualiza cada "
                      "trimestre. El 10-K de la SEC es el informe anual: cubre un ejercicio cerrado y llega 2 o 3 "
                      "meses después. Para la misma empresa y el mismo día, el PER puede salir distinto según "
                      "cuál se use."),
}

# Every metric's help is a term (#197): the ⓘ of Ranking, company page and Comparar and the Ayuda
# glossary read the same text. Identity fields are not metrics.
NOT_TERMS = frozenset({"name", "sector"})


def glossary(metric_info: dict[str, dict[str, str]]) -> list[dict[str, str]]:
    entries = [{"key": key, "term": term, "definition": definition} for key, (term, definition) in TERMS.items()]
    entries += [{"key": key, "term": info["label"], "definition": info["help"]}
                for key, info in metric_info.items() if key not in NOT_TERMS]
    return sorted(entries, key=lambda entry: entry["term"].lower())
