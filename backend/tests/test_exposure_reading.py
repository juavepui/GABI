"""¿Tengo demasiados huevos en una cesta? (#324): sentences without invented numbers, a warning limit, never a max."""

import re

from gabi.domain.portfolio import exposure_reading as reading

SECTORS = [
    {"sector": "Information Technology", "positions": 8, "weight_pct": 40.0, "index_weight_pct": 31.5,
     "difference_pp": 8.5},
    {"sector": "Health Care", "positions": 2, "weight_pct": 10.0, "index_weight_pct": 12.0, "difference_pp": -2.0},
    {"sector": "Energy", "positions": 0, "weight_pct": 0.0, "index_weight_pct": 3.4, "difference_pp": -3.4},
]
OVER = [{"kind": "sector", "name": "Information Technology", "positions": 8, "weight_pct": 40.0, "limit_pct": 25.0},
        {"kind": "industry", "name": "Software", "positions": 5, "weight_pct": 25.0, "limit_pct": 20.0}]


def _numbers(item: dict) -> None:
    allowed = set()

    def collect(value):
        if isinstance(value, dict):
            for inner in value.values():
                collect(inner)
        elif isinstance(value, list):
            for inner in value:
                collect(inner)
        elif isinstance(value, int | float) and not isinstance(value, bool):
            allowed.update({f"{value:.1f}".replace(".", ","), str(int(value))})

    collect(item["values"])
    for number in re.findall(r"\d+(?:,\d+)?", item["text"].replace("S&P 500", "")):
        assert number in allowed, (number, item["text"])


def test_plan_sectors_names_the_warning_and_the_biggest_differences():
    item = reading.plan_sectors(SECTORS, OVER, 25.0)
    assert item["text"] == ("Pasa tu límite de aviso del 25,0 %: Information Technology (40,0 %). Frente al S&P 500, "
                            "la cartera propuesta pesa más en Information Technology (40,0 % frente a 31,5 %) y "
                            "menos en Energy (0,0 % frente a 3,4 %).")
    _numbers(item)
    assert not re.search(r"\b(máximo|vender|vende|obligatori)", item["text"], re.I)


def test_plan_sectors_without_warnings_or_index_says_so():
    calm = reading.plan_sectors(SECTORS, [], 25.0)
    assert calm["text"].endswith("Ningún sector pasa tu límite de aviso del 25,0 %.")
    blind = reading.plan_sectors([{**row, "index_weight_pct": None, "difference_pp": None} for row in SECTORS], [], 25)
    assert blind["text"].startswith("Sin el peso de cada sector en el S&P 500 para comparar.")
    assert reading.plan_sectors([], [], 25)["text"] == "La cartera propuesta todavía no tiene empresas."


def test_holdings_issuers_names_the_largest_and_counts_the_ones_over_the_limit():
    issuers = [{"issuer": "Apple", "weight": 0.18, "exceeds": True}, {"issuer": "Visa", "weight": 0.12, "exceeds": True},
               {"issuer": "Pepsi", "weight": 0.05, "exceeds": False}]
    item = reading.holdings_issuers(issuers, 0.10)
    assert item["text"] == ("Tu mayor posición es Apple, con el 18,0 % de tu cartera; 2 empresas pasan tu límite por "
                            "empresa del 10,0 %.")
    _numbers(item)
    one = reading.holdings_issuers([{**issuers[0], "exceeds": False}], 0.25)
    assert one["text"].endswith("ninguna pasa tu límite por empresa del 25,0 %.")
    assert reading.holdings_issuers([], 0.1)["text"] == "Mi cartera no tiene posiciones valoradas."
