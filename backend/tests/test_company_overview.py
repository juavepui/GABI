"""Las primeras líneas de la ficha (#310): plain sentences without invented numbers, and the typical move."""

import re

import pytest
from fastapi.testclient import TestClient
from market_fixture import TODAY, seed_fixture

from gabi.domain.market import company_overview as overview
from gabi.infrastructure.settings import Settings
from gabi_api.bootstrap import create_app


def _numbers_come_from(text: str, values: dict, *, skip: tuple[str, ...] = ()) -> None:
    allowed = set()

    def collect(value):
        if isinstance(value, dict):
            for item in value.values():
                collect(item)
        elif isinstance(value, int | float) and not isinstance(value, bool):
            allowed.update({f"{value:.1f}".replace(".", ","), str(int(value))})

    collect(values)
    for word in skip:
        text = text.replace(word, "")
    for number in re.findall(r"\d+(?:,\d+)?", text.replace("de 100", "")):
        assert number in allowed, (number, text)


@pytest.mark.parametrize(("score", "word", "level"), [(70.0, "alta", "high"), (69.9, "media", "medium"),
                                                      (40.1, "media", "medium"), (40.0, "baja", "low")])
def test_score_level_limits(score, word, level):
    result = overview.headline(name="Okta", symbol="OKTA", sector="Information Technology",
                               row={"composite_score": score}, rank=3, universe=503, warning_text=None)
    assert result["level"] == level and f"es {word}:" in result["text"]


def test_headline_names_the_weakest_block_or_the_warning_and_invents_no_number():
    row = {"composite_score": 78.4, "value_score": 35.2, "quality_score": 80.0, "momentum_score": 90.0,
           "risk_score": 60.0}
    result = overview.headline(name="Okta", symbol="OKTA", sector="Information Technology", row=row, rank=12,
                               universe=503, warning_text=None)
    assert result["text"] == ("Okta es una empresa del sector Information Technology. Su puntuación GABI es alta: "
                              "78,4 de 100, puesto 12 de 503; su punto más débil es la valoración (si su precio es "
                              "razonable) (35,2 de 100).")
    _numbers_come_from(result["text"], result["values"])
    warned = overview.headline(name=None, symbol="OKTA", sector=None, row=row, rank=12, universe=503,
                               warning_text="Resultados en 3 días")
    assert warned["text"].startswith("OKTA: sector no disponible.")
    assert warned["text"].endswith("; ojo: resultados en 3 días.")
    no_weak = overview.headline(name="A", symbol="A", sector="X", row={**row, "value_score": 55.0}, rank=1,
                                universe=10, warning_text=None)
    assert no_weak["text"].endswith("puesto 1 de 10.")
    unscored = overview.headline(name="A", symbol="A", sector="X", row={}, rank=10, universe=10, warning_text=None)
    assert unscored["level"] is None and "no tiene puntuación" in unscored["text"]


def test_typical_move_uses_the_latest_eight_absolute_reactions():
    reactions = [50.0, None, -2.0, 4.0, -6.0, 8.0, -10.0, 12.0, -14.0, 16.0]  # Oldest first.
    result = overview.typical_move(reactions)
    assert result["count"] == 8 and result["enough"] is True
    assert result["mean_abs_pct"] == pytest.approx(9.0) and result["max_abs_pct"] == 16.0  # The 50 % is older.
    assert result["text"] == ("El día de resultados su precio suele moverse un ±9,0 % (media de las últimas 8 "
                              "presentaciones; la mayor, ±16,0 %).")


def test_few_reactions_are_marked_as_orientative_and_none_is_said():
    few = overview.typical_move([3.0, -5.0])
    assert few["enough"] is False and few["count"] == 2
    assert few["text"].endswith("Son menos de 4: tómalo solo como orientación.")
    empty = overview.typical_move([None])
    assert empty["count"] == 0 and empty["mean_abs_pct"] is None and empty["text"].startswith("Sin datos")


def test_company_api_returns_the_headline_and_research_the_typical_move(tmp_path):
    seed_fixture(tmp_path, companies=30)
    with TestClient(create_app(Settings(tmp_path), today=lambda: TODAY)) as api:
        body = api.get("/api/v1/companies/T000").json()
        research = api.get("/api/v1/companies/T000/research")
    headline = body["headline"]
    assert headline["text"].startswith(body["company"]["name"] or "T000")
    assert f"puesto {body['company']['rank']} de" in headline["text"]
    _numbers_come_from(headline["text"], headline["values"], skip=("T000",))
    assert research.status_code == 200, research.text
    assert research.json()["typical_move"]["count"] == 0  # The fixture stores no results history.
