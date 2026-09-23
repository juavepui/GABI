import pytest

from gabi.valuation_expectations import expectations_metrics, reverse_dcf_growth


def test_reverse_dcf_recovers_known_growth():
    # Use the same equation as the implementation to create a value at 10%.
    from gabi.valuation_expectations import _present_value
    fcf = 100.0
    enterprise_value = _present_value(fcf, 0.10, 0.0, 0.09, 0.025, 5)
    assert reverse_dcf_growth(enterprise_value, fcf) == pytest.approx(0.10)


def test_reverse_dcf_rejects_unusable_cash_flow_and_invalid_assumptions():
    assert reverse_dcf_growth(1000, 0) is None
    assert reverse_dcf_growth(1000, 100, discount_rate=.02, terminal_growth=.025) is None
    assert reverse_dcf_growth(None, 100) is None


def test_expectations_gap_is_historical_minus_implied():
    result = expectations_metrics(enterprise_value=1000, latest_fcf=100, historical_fcf_cagr=.20)
    assert result["implied_fcf_growth"] is not None
    assert result["expectations_gap"] == pytest.approx(.20 - result["implied_fcf_growth"])
