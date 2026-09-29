"""#36: rescoring keeps the control's eligible set; the decision rule is the registered one."""

import numpy as np
import pandas as pd

from gabi import r3_experiment as r3
from gabi import scoring


def _table(n=12):
    rng = np.random.default_rng(0)
    frame = pd.DataFrame({metric: rng.normal(size=n) for group in scoring.SCORE_METRICS.values() for metric in group},
                         index=[f"S{i}" for i in range(n)])
    frame["sector"] = "Tech"
    frame["quality_persistence_score"] = np.linspace(0, 1, n)
    frame["roic_persistence_std"] = np.linspace(1, 0, n)
    frame["expectations_gap"] = np.linspace(-0.1, 0.1, n)
    frame["roic_years"] = [2] + [5] * (n - 1)
    frame.loc["S1", "pe"] = np.nan
    scored = scoring.build_scores(frame, scoring.DEFAULT_WEIGHTS)
    scored.loc["S2", "score_coverage"] = 0.6  # ineligible in the control
    return scored


def test_control_rescore_reproduces_and_variants_keep_the_control_eligible_set():
    table = _table()
    control = r3.rescore(table, "control_composite", "2020-01-02")
    assert np.allclose(control["composite_score"].dropna().sort_index(),
                       table.loc[control["composite_score"].dropna().index, "composite_score"].sort_index())
    variant = r3.rescore(table, "e6a_calidad_persistente", "2020-01-02")
    assert pd.isna(variant.loc["S2", "composite_score"]) and variant.loc["S2", "score_coverage"] == 0.6
    assert set(variant["composite_score"].dropna().index) == set(control["composite_score"].dropna().index)
    # Sorted by the new score: the engine takes candidates in table order.
    assert variant["composite_score"].dropna().is_monotonic_decreasing
    # Persistence metrics need 3 fiscal years; S0 has 2.
    assert "quality_persistence_score_pct" in variant and pd.isna(variant.loc["S0", "quality_persistence_score_pct"])


def _analysis(cagr_c, cagr_v, windows_v, es_v=0.03, dd_v=-0.30, p=0.01, dsr=0.99):
    def windows(full, subs, es, dd):
        result = {"completa_2011_2025": {"cagr_net": full, "es_95": es, "drawdown": dd}}
        result.update({w: {"cagr_net": v} for w, v in zip(r3.SUB_WINDOWS, subs, strict=True)})
        return result
    return {"control_composite": {"ventanas": {"top20": windows(cagr_c, [0.1, 0.1, 0.1], 0.03, -0.30)}},
            "v": {"ventanas": {"top20": windows(cagr_v, windows_v, es_v, dd_v)},
                  "frente_al_control": {"p_holm": p}, "dsr": {"dsr": dsr}}}


def test_decision_rule():
    assert r3.decide(_analysis(0.17, 0.19, [0.11, 0.12, 0.09]), "v")["decision"] == "adoptar"
    assert r3.decide(_analysis(0.17, 0.19, [0.11, 0.12, 0.09], p=0.2), "v")["decision"] == \
        "pendiente_validacion_prospectiva"
    assert r3.decide(_analysis(0.17, 0.175, [0.11, 0.12, 0.09]), "v")["decision"] == "descartar"
    assert r3.decide(_analysis(0.17, 0.19, [0.11, 0.09, 0.09]), "v")["decision"] == "descartar"
    assert r3.decide(_analysis(0.17, 0.19, [0.11, 0.12, 0.09], es_v=0.034), "v")["decision"] == "descartar"
    assert r3.decide(_analysis(0.17, 0.19, [0.11, 0.12, 0.09], dd_v=-0.34), "v")["decision"] == "descartar"


def test_spec_is_frozen_and_counts_all_documented_trials():
    assert r3.SPEC["multiple_testing"]["dsr_trials"] == 29
    assert r3.VARIANTS == ("e6a_calidad_persistente", "e6b_riesgo_756") and r3.RISK_WINDOW == 756
    assert len(r3.spec_hash()) == 64
