"""#35: attribution of portfolio differences and the pre-registered conclusion rule."""

import pandas as pd

from gabi import historical_revalidation as hr


def _table(rows):
    columns = ["entity_id", "price_source", "composite_score", "score_coverage", *hr.FUNDAMENTAL, *hr.PRICE]
    frame = pd.DataFrame(rows).set_index("symbol")
    return frame.reindex(columns=columns)


BASE = {"entity_id": "cik:1", "price_source": "yahoo", "composite_score": 80.0, "score_coverage": 1.0,
        **{metric: 1.0 for metric in hr.FUNDAMENTAL + hr.PRICE}}


def test_exit_reasons_follow_the_accreditation_order():
    reference = _table([{"symbol": s, **BASE} for s in ("A", "B", "C", "D", "E", "F", "G")])
    other = _table([
        {"symbol": "A", **BASE, "entity_id": None},
        {"symbol": "B", **BASE, "price_source": None},
        {"symbol": "C", **BASE, "score_coverage": 0.5},
        {"symbol": "D", **BASE, hr.FUNDAMENTAL[0]: 2.0},
        {"symbol": "E", **BASE, hr.PRICE[0]: None},
        {"symbol": "F", **BASE},
    ])
    reasons = {s: hr.classify_exit(s, reference, other, accredited=True) for s in "ABCDEFG"}
    assert reasons == {"A": "identidad_no_acreditada", "B": "sin_precio_acreditado", "C": "no_elegible",
                       "D": "desplazada_fundamentales", "E": "desplazada_precio",
                       "F": "desplazada_por_otras_entradas", "G": "fuera_de_la_composicion"}
    # On the operational path identity/price availability is not an accreditation test.
    assert hr.classify_exit("A", reference, other, accredited=False) == "desplazada_por_otras_entradas"


def test_entry_reasons():
    reference = _table([{"symbol": "X", **BASE, "composite_score": None}, {"symbol": "Y", **BASE}])
    other = _table([{"symbol": s, **BASE} for s in ("X", "Y", "Z")])
    assert hr.classify_entry("Z", reference, other) == "miembro_ausente_en_la_referencia"
    assert hr.classify_entry("X", reference, other) == "no_elegible_en_la_referencia"
    assert hr.classify_entry("Y", reference, other) == "sube_por_otras_salidas"


def _summary(cagr, spy, t, dsr):
    return {"acreditado-38-2016": {"metricas": {"top20": {"estrategia": {"cagr": cagr}, "spy": {"cagr": spy}}},
                                   "exceso_trimestral": {"t": t}, "overfitting": {"dsr": {"dsr": dsr}}}}


def test_conclusion_rule_is_the_registered_one():
    assert hr.conclusion(_summary(0.10, 0.12, 3.0, 0.99)) == "no_sobrevive"
    assert hr.conclusion(_summary(0.14, 0.12, 1.5, 0.99)) == "sobrevive_sin_significacion"
    assert hr.conclusion(_summary(0.14, 0.12, 2.5, 0.90)) == "sobrevive_sin_significacion"
    assert hr.conclusion(_summary(0.14, 0.12, 2.5, 0.97)) == "sobrevive_y_es_significativa"
    failed = _summary(0.14, 0.12, 2.5, 0.97)
    failed["acreditado-38-2016"]["overfitting"] = {"error": "cobertura"}
    assert hr.conclusion(failed) == "sobrevive_sin_significacion"


def test_variants_share_dates_and_only_the_principal_runs_from_2010():
    assert {v.start for k, v in hr.VARIANTS.items() if k != "acreditado-38"} == {"2016-01-02"}
    assert hr.VARIANTS["acreditado-38"].start == "2010-01-02" and hr.VARIANTS["acreditado-38"].fiscal_alignment
    assert not hr.VARIANTS["operativo"].periods and not hr.VARIANTS["operativo"].fiscal_alignment
    assert hr.STOP == "2025-07-03" and hr.PRIMARY_TOP == 20
