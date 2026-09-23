"""Reconcile published experiment artifacts without querying the private database."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from gabi.factor_stability import content_hash

REPORT = Path(__file__).resolve().parents[1] / "docs/rotation-experiment"


def test_saved_trials_reconcile_returns_costs_and_all_39_quarters():
    audit = json.loads((REPORT / "audit.json").read_text(encoding="utf-8"))
    assert audit["status"] == "complete"
    assert audit["future"]["status"] == "not_evaluated"
    assert len(audit["daily_valuation_checks"]) == 117
    for filename, digest in audit["artifacts_canonical_sha256"].items():
        assert content_hash(REPORT / filename) == digest
    quarterly = pd.read_csv(REPORT / "quarterly-returns.csv", index_col=0)
    assert len(quarterly) == 39
    for name in audit["protocol"]["variants"]:
        nav = pd.read_csv(REPORT / f"{name}-nav.csv", index_col=0, parse_dates=True)
        periods = pd.read_csv(REPORT / f"{name}-periods.csv")
        rows = {r["window"]: r for r in audit["metrics"] if r["variant"] == name}
        full = rows["full_history"]
        assert full["n_periods"] == len(periods) == 39
        assert (1 + quarterly[name]).prod() == pytest.approx(nav.strategy.iloc[-1] / 100000.)
        years = (nav.index[-1] - nav.index[0]).days / 365.25
        assert full["cagr_net"] == pytest.approx((nav.strategy.iloc[-1] / 100000.) ** (1 / years) - 1)
        assert full["cost_total"] == pytest.approx(periods.comision_pagada.sum() + periods.spread_pagado.sum())
        first, second = rows["development_retrospective"], rows["validation_retrospective"]
        assert first["final_value"] == second["initial_value"]
        assert first["n_obs"] + second["n_obs"] == full["n_obs"]
        assert first["cost_total"] + second["cost_total"] == pytest.approx(full["cost_total"])


def test_saved_control_is_same_as_prior_full_universe_audit():
    old = pd.read_csv(REPORT.parent / "full-universe-audit/v2-top20-nav.csv", index_col=0)
    new = pd.read_csv(REPORT / "control_composite-nav.csv", index_col=0)
    assert old.index.tolist() == new.index.tolist()
    np.testing.assert_allclose(old.strategy, new.strategy, rtol=1e-12)
