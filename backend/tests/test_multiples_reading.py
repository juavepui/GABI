"""¿Está cara o barata para ella? (#326): median-based readings, few years, negatives and the quality caveat."""

import re

import pytest

from gabi.domain.market import multiples_reading as reading

QUALITY_WEAK = [{"block": "Rentabilidad", "verdict": "fail"}, {"block": "Rentabilidad", "verdict": "fail"},
                {"block": "Calidad de la caja", "verdict": "pass"}]
QUALITY_OK = [{"block": "Rentabilidad", "verdict": "pass"}, {"block": "Calidad de la caja", "verdict": "pass"},
              {"block": "Rentabilidad", "verdict": "fail"}]


def _numbers_come_from(item: dict) -> None:
    allowed = set()
    for value in item.values():
        if isinstance(value, int | float) and not isinstance(value, bool):
            allowed |= {f"{value:.1f}".replace(".", ","), str(int(value))}
    text = item["text"].replace(item["label"], "")
    for number in re.findall(r"\d+(?:,\d+)?", text):
        assert number in allowed or number == str(reading.MIN_YEARS), (number, item["text"])


def test_cheaper_than_its_median_counts_the_years_and_ignores_one_odd_year():
    # One year with a collapsed profit (PE 95) stretches the range; the median keeps the reading honest.
    item = reading.own("pe", 14.0, [18.0, 20.0, 16.0, 95.0, 12.0], financial=False, weak=False)
    assert item["status"] == "ok" and item["median"] == 18.0 and item["side"] == "cheaper"
    assert (item["min"], item["max"], item["years"]) == (12.0, 95.0, 5)
    assert item["pricier_years"] == 4 and item["cheaper_years"] == 1
    assert item["text"] == ("PER de 14,0: más barata de lo habitual en ella (mediana de 18,0); cotizó más cara en "
                            "4 de sus últimos 5 años.")
    _numbers_come_from(item)


@pytest.mark.parametrize(("current", "side"), [(15.2, "cheaper"), (15.3, "inline"), (15.4, "inline"),
                                               (20.7, "inline"), (20.8, "pricier")])
def test_the_inline_band_is_fifteen_percent_of_the_median(current, side):
    assert reading.own("pe", current, [18.0, 18.0, 18.0], financial=False, weak=False)["side"] == side


def test_no_conclusion_with_few_years_negatives_missing_or_banks():
    few = reading.own("ev_ebit", 10.0, [9.0, None, -3.0], financial=False, weak=False)
    assert few["status"] == "few_years" and few["side"] is None and few["median"] is None
    assert "con menos de 3 no se saca conclusión" in few["text"]
    _numbers_come_from(few)
    assert reading.own("pe", -12.0, [10.0] * 5, financial=False, weak=False)["status"] == "negative"
    assert reading.own("pe", None, [10.0] * 5, financial=False, weak=False)["status"] == "missing"
    bank = reading.own("ev_ebitda", 8.0, [10.0] * 5, financial=True, weak=False)
    assert bank["status"] == "not_applicable" and "bancos" in bank["text"]


def test_cheap_with_weak_quality_says_why_it_may_be_cheap_and_never_recommends():
    assert reading.weak_quality(QUALITY_WEAK) and not reading.weak_quality(QUALITY_OK)
    assert not reading.weak_quality(QUALITY_WEAK[:2])  # Fewer than 3 evaluated.
    items = reading.own_readings({"pe": 10.0, "ev_ebitda": 30.0}, [{"pe": 20.0, "ev_ebitda": 15.0}] * 4,
                                 QUALITY_WEAK, financial=False)
    pe, ev_ebitda = items[0], items[1]
    assert pe["text"].endswith("a veces está barata por eso.")
    assert "Ojo" not in ev_ebitda["text"] and ev_ebitda["side"] == "pricier"
    for item in items:
        assert not re.search(r"\b(compra|comprar|oportunidad|ganga|chollo)\b", item["text"], re.I)


def test_sector_reading():
    item = reading.sector("pe", 12.0, 20.0, 31)
    assert item["side"] == "cheaper"
    assert item["text"] == "PER de 12,0: más barata que la mediana de su sector (20,0, 31 empresas)."
    _numbers_come_from(item)
    assert reading.sector("pe", 12.0, None, 2)["status"] == "missing"
    assert [row["key"] for row in reading.sector_readings({}, {}, 0)] == ["pe", "ev_ebitda", "ev_ebit", "ev_fcf"]
