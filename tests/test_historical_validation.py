import math

import pandas as pd

from gabi import historical_validation as hv


def _table(rows):
    columns = ["entity_id", "price_source", "composite_score", "score_coverage", *hv.ALL_METRICS]
    return pd.DataFrame(rows, columns=["symbol", *columns]).set_index("symbol")


def test_coverage_diagnostic_separates_data_failures_and_marks_inconclusive_cuts(monkeypatch):
    full = [1.0] * len(hv.ALL_METRICS)
    table = _table([
        ["OK", "cik:1", "yahoo", 70.0, 1.0, *full],
        ["NOID", None, None, None, 0.0, *[None] * len(hv.ALL_METRICS)],
        ["NOPRICE", "cik:3", None, None, 0.2, *[1.0] * 3, *[None] * (len(hv.ALL_METRICS) - 3)],
        ["THIN", "cik:4", "wiki", 40.0, 0.5, *[1.0] * 6, *[None] * (len(hv.ALL_METRICS) - 6)],
    ])
    monkeypatch.setattr(hv, "_audit_rebalance", lambda date: {"as_of": "2012-03-31", "usable_pct": 90.0}
                        if date >= "2012" else {"as_of": "2010-03-31", "usable_pct": 78.0})
    coverage = hv.coverage_by_rebalance({"2012-04-02": table, "2010-04-02": table}, executed={"2012-04-02"})
    row = coverage.set_index("fecha").loc["2012-04-02"]
    assert (row.constituyentes, row.identidad_acreditada, row.precio_acreditado) == (4, 3, 2)
    assert row["13_metricas_calculables"] == 1 and row.elegibles == 1
    assert (row.identidad_no_acreditada, row.sin_precio_acreditado, row.cobertura_metricas_inferior_70) == (1, 1, 1)
    # 1/4 eligible (< 50 %): even an executed period is not conclusive.
    assert not row.concluyente
    early = coverage.set_index("fecha").loc["2010-04-02"]
    assert not early.ejecutado and not early.concluyente and early.cobertura_precio_auditoria == 0.78


def test_compound_ignores_missing_periods():
    assert hv._compound(pd.Series([0.1, None, -0.1])) == 1.1 * 0.9 - 1
    assert math.isnan(hv._compound(pd.Series([None, None], dtype=float)))
