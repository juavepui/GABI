"""¿Aguantaría una crisis? ¿Compensa elegir acciones? (#325): sentences from data, honest about evidence."""

import re

from gabi.domain.portfolio import stress_reading as reading

ROWS = [
    {"id": "market_-35", "label": "Mercado −35 %, como en 2020", "change": -0.35, "change_eur": -3850.0,
     "exceeds_tolerance": True},
    {"id": "euro_-10", "label": "El euro baja un 10 % frente al dólar", "change": 0.11, "change_eur": 1210.0,
     "exceeds_tolerance": False},
    {"id": "gap_-7", "label": "Apertura con hueco del −7 %", "change": -0.07, "change_eur": -770.0,
     "exceeds_tolerance": False},
]


def _numbers(item: dict) -> None:
    allowed = set()

    def collect(value):
        if isinstance(value, dict):
            for inner in value.values():
                collect(inner)
        elif isinstance(value, int | float) and not isinstance(value, bool):
            for number in (value, abs(value), abs(value) * 100):
                allowed.update({f"{number:.1f}".replace(".", ","), str(int(number)),
                                f"{number:,.0f}".replace(",", ".")})
        elif isinstance(value, str):
            allowed.update(re.findall(r"\d+(?:[.,]\d+)?", value))

    collect(item["values"])
    for number in re.findall(r"\d+(?:\.\d{3})*(?:,\d+)?", item["text"].replace("S&P 500", "")):
        assert number in allowed, (number, item["text"])


def test_crisis_sentence_names_the_worst_case_and_the_tolerance_and_never_says_sell():
    item = reading.scenarios(ROWS, 0.20, 11000.0)
    assert item["text"] == ("Con los 11.000 € de hoy, la peor de estas crisis (Mercado −35 %, como en 2020) te "
                            "quitaría 3.850 €, el 35,0 %. Aceptas perder hasta el 20,0 % (2.200 €): 1 de los 3 "
                            "escenarios lo pasa. Es motivo para revisar tu plan, no para vender.")
    assert item["values"]["tolerance_eur"] == 2200.0
    _numbers(item)
    calm = reading.scenarios([{**row, "exceeds_tolerance": False} for row in ROWS], 0.4, 11000.0)
    assert calm["text"].endswith("ninguno de los escenarios lo pasa.")
    assert reading.scenarios([], 0.2, 0.0)["text"] == "Sin valor actual con el que calcular las crisis."


def _alternative(label, value, drawdown):
    return {"label": label, "performance": {"final_value_eur": value, "max_drawdown": drawdown}}


def test_alternatives_name_best_worst_and_calmest_and_say_it_is_not_proven():
    rows = [_alternative("Activa: tu cartera", 12300.0, -0.28), _alternative("Mixta: 50 % índice", 12100.0, -0.22),
            _alternative("Indexada: SPY", 11800.0, -0.19)]
    item = reading.alternatives(rows)
    assert item["text"].startswith("Con tus mismas compras, la opción que más valdría hoy es «Activa: tu cartera» "
                                   "(12.300 €) y la que menos, «Indexada: SPY» (11.800 €). La que menos cayó en su "
                                   "peor momento fue «Indexada: SPY» (−19,0 %).")
    assert "todavía no está demostrado que la regla de GABI gane al S&P 500" in item["text"]
    assert "puede ser suerte" in item["text"]
    # «tus mismas compras» are the purchases already made; an order to buy or sell is never written.
    assert not re.search(r"\b(comprar|compra|vender|vende|recomiend\w*|recomend\w*)\b", item["text"], re.I)
    _numbers(item)
    assert reading.alternatives(rows[:1])["text"] == "Sin datos suficientes para comparar las opciones."
