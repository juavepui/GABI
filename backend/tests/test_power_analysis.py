"""#39: power formulas."""

import math

from gabi.domain.research import power_analysis as pa


def test_quarters_needed_matches_the_closed_form_and_inverts_the_detectable_effect():
    n = pa.quarters_needed(0.01, 0.04)
    assert math.isclose(n, ((1.6448536 + 0.8416212) * 4) ** 2, rel_tol=1e-6)
    assert math.isclose(pa.minimum_detectable(0.04, n), 0.01, rel_tol=1e-9)
    assert math.isclose(pa.power_at(0.01, 0.04, n), 0.80, rel_tol=1e-6)
    assert pa.quarters_needed(0.0, 0.04) == math.inf


def test_report_uses_only_the_published_series_and_the_given_dsr_bar():
    import pandas as pd

    periods = pd.DataFrame({"fecha": ["2015-01-02", "2016-01-02", "2016-04-02", "2016-07-02"],
                            "retorno": [0.05, 0.03, None, 0.04], "spy": [0.02, 0.01, 0.0, 0.02]})
    bench = pd.DataFrame({"fecha": periods.fecha, "universo_elegible_ew": [0.01, 0.02, 0.0, None]})
    report = pa.report(periods, bench, 1.25)
    tests = {row["prueba"]: row["trimestres"] for row in report["cartera"]}
    assert tests == {"vs_spy_2011_2025": 3, "vs_universo_2011_2025": 2, "vs_spy_2016_2025": 2, "vs_universo_2016_2025": 1}
    assert report["multiples_pruebas"]["sharpe_maximo_esperado_por_azar_anual"] == 1.25
    assert len(report["seccion_cruzada"]) == len(pa.IC_SCENARIOS) * len(pa.IC_SD_SCENARIOS)
