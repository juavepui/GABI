"""Etiquetas en palabras del panel macro (#309): fixed rules, tested at their limits."""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from gabi.domain.market import macro_labels as rules
from gabi.domain.market.fred import SERIES
from gabi.domain.market.macro_series import BLOCK, NEW_SERIES, macro_metadata, synchronized_series
from gabi.infrastructure.settings import Settings
from gabi_api.bootstrap import create_app


def _row(value, change=None, day="2026-11-01"):
    return {"latest_value": value, "change_3m": change, "latest_date": day}


@pytest.mark.parametrize(("value", "label", "tone"), [
    (1.5, "Inflación cerca del objetivo", "good"), (3.0, "Inflación cerca del objetivo", "good"),
    (3.01, "Inflación por encima del objetivo", "bad"), (5.0, "Inflación por encima del objetivo", "bad"),
    (5.01, "Inflación alta", "bad")])
def test_inflation_limits(value, label, tone):
    result = rules.inflation(_row(value))
    assert (result["label"], result["tone"], result["series_id"], result["value"]) == (label, tone, "CPIAUCSL", value)


@pytest.mark.parametrize(("value", "label"), [
    (0.29, "Empleo sólido"), (0.3, "Empleo debilitándose"), (0.49, "Empleo debilitándose"),
    (0.5, "Señal de recesión")])
def test_sahm_limits(value, label):
    assert rules.growth(_row(value))["label"] == label


@pytest.mark.parametrize(("value", "change", "label"), [
    (101.0, 1.0, "Estable"),  # +1,0 % exactly.
    (102.0, 2.0, "Aumentando"), (98.0, -2.0, "Bajando"), (99.0, -1.0, "Estable")])
def test_liquidity_is_the_percentage_change_and_never_judged(value, change, label):
    result = rules.liquidity(_row(value, change))
    assert result["label"] == label and result["tone"] == "neutral"
    assert result["value"] == pytest.approx(100 * change / (value - change))


def test_conditions_use_nfci_and_fall_back_to_the_credit_spread():
    assert rules.conditions(_row(-0.01), None)["label"] == "Holgadas"
    assert rules.conditions(_row(0.0), None)["label"] == "Más tensas que la media"
    assert rules.conditions(None, _row(3.99))["label"] == "Holgadas"
    assert rules.conditions(None, _row(4.0))["label"] == "Normales"
    assert rules.conditions(None, _row(6.0))["label"] == "Normales"
    spread = rules.conditions(_row(None), _row(6.01))
    assert spread["label"] == "Tensas" and spread["series_id"] == "BAMLH0A0HYM2"


def test_missing_data_is_said_instead_of_guessed():
    for label in rules.labels([]):
        assert label["label"] == "Sin datos" and label["series_id"] is None and label["value"] is None
        assert label["rule"].startswith("Faltan los datos de")
    assert rules.liquidity(_row(100.0, None))["label"] == "Sin datos"  # No value 3 months ago.
    assert [label["block"] for label in rules.labels([])] == list(rules.BLOCKS)


def test_new_series_are_refreshed_without_touching_the_captured_ones():
    assert set(NEW_SERIES) == {"NFCI", "UNRATE", "ICSA", "T10YIE"} and not set(NEW_SERIES) & set(SERIES)
    assert set(synchronized_series()) == set(SERIES) | set(NEW_SERIES)
    # The regular FRED refresh downloads them too; the captured quality report keeps the original nine.
    from gabi.infrastructure.legacy import fred as refresh
    assert set(refresh.SERIES) == set(synchronized_series())
    # Every series shown belongs to exactly one block, and every block lists only known series.
    assert set(BLOCK) == set(synchronized_series())
    metadata = macro_metadata({key: dict(meta) for key, meta in synchronized_series().items()})
    assert all(meta["units_param"] == "lin" and meta["help"] for meta in NEW_SERIES.values())
    assert metadata["ICSA"]["frequency"] == "weekly" and metadata["NFCI"]["block"] == "conditions"


def test_macro_api_publishes_one_label_per_block_with_its_date_and_rule(tmp_path):
    with sqlite3.connect(tmp_path / "gabi.db") as db:
        db.execute("CREATE TABLE macro_series(series_id TEXT,date TEXT,value REAL)")
        db.executemany("INSERT INTO macro_series VALUES(?,?,?)", [
            ("CPIAUCSL", "2026-09-01", 2.9), ("SAHMREALTIME", "2026-09-01", 0.2),
            ("NFCI", "2026-10-24", -0.5), ("ICSA", "2026-10-25", 230000.0),
            ("WALCL", "2026-06-03", 6_800_000.0), ("WALCL", "2026-10-29", 6_600_000.0)])
    with TestClient(create_app(Settings(tmp_path))) as api:
        body = api.get("/api/v1/market/macro").json()
    labels = {label["block"]: label for label in body["labels"]}
    assert labels["inflation_rates"]["label"] == "Inflación cerca del objetivo"
    assert labels["growth_jobs"]["label"] == "Empleo sólido"
    assert (labels["conditions"]["label"], labels["conditions"]["date"]) == ("Holgadas", "2026-10-24")
    assert labels["liquidity"]["label"] == "Bajando" and labels["liquidity"]["value"] == pytest.approx(-200 / 68)
    rows = {row["series_id"]: row for row in body["items"]}
    assert (rows["ICSA"]["unit"], rows["ICSA"]["latest_value"], rows["ICSA"]["block"]) == (
        "personas", 230000.0, "growth_jobs")
    assert body["affects_score"] is False
