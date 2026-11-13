"""NSI-v1 preregistered statistics (#252): bootstrap lower bound, FF5+UMD alpha and the decision rule."""

import numpy as np
import pandas as pd
import pytest

from gabi.domain.research import nsi_statistics as stats


def test_monthly_returns_of_a_daily_index_start_from_its_first_value():
    days = pd.bdate_range("2020-01-01", "2020-03-31")
    index = pd.Series(np.linspace(1.0, 1.1, len(days)), index=days)
    months = stats.monthly(index)
    assert len(months) == 3 and (1 + months).prod() == pytest.approx(1.1)


def test_the_lower_bound_is_below_the_mean_and_reproducible():
    rng = np.random.default_rng(1)
    excess = pd.Series(rng.normal(0.002, 0.02, 120))
    first, again = stats.lower_bound(excess), stats.lower_bound(excess)
    assert first == again and first["lower_bound_annual"] < first["mean_annual"]
    assert stats.lower_bound(excess.iloc[:6])["lower_bound_annual"] is None


def test_alpha_recovers_a_known_intercept_and_loadings():
    rng = np.random.default_rng(2)
    months = pd.period_range("2011-07", periods=168, freq="M")
    factors = pd.DataFrame(rng.normal(0, 0.03, (168, 6)), columns=list(stats.FACTORS))
    factors["RF"] = 0.001
    factors["date"] = months.to_timestamp()
    values = (0.004 + factors["RF"] + 1.0 * factors["Mkt-RF"] + 0.5 * factors["CMA"]
              + rng.normal(0, 0.001, 168)).to_numpy()
    returns = pd.Series(values, index=months.to_timestamp("M"))
    result = stats.factor_alpha(returns, factors)
    assert result["alpha_annual"] == pytest.approx(0.048, abs=0.005) and not result["contains_zero"]
    assert result["loadings"]["CMA"] == pytest.approx(0.5, abs=0.02)


def test_the_decision_follows_the_preregistered_order():
    clean = {"contains_zero": False}
    assert stats.decide(-0.01, [0.01, 0.01, 0.01], clean)["reason"] == "net_excess_not_positive"
    assert stats.decide(0.02, [-0.01, -0.02, 0.01], clean)["reason"] == "lower_bound_negative_in_two_windows"
    assert stats.decide(0.02, [-0.01, 0.01, 0.01], {"contains_zero": True})["label"] == "factor_exposure"
    assert stats.decide(0.02, [-0.01, 0.01, 0.01], clean)["label"] == "continue_to_prospective"
