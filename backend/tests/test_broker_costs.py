import pytest

from gabi import broker_costs


def test_effective_trade_cost_bps_matches_manual_calculation():
    # 1$ sobre una posición de 500$ = 0.20% = 20 puntos básicos.
    assert broker_costs.effective_trade_cost_bps(500) == pytest.approx(20.0)


def test_effective_trade_cost_bps_scales_inversely_with_position_size():
    small = broker_costs.effective_trade_cost_bps(200)
    large = broker_costs.effective_trade_cost_bps(2000)
    assert small == pytest.approx(large * 10)


def test_effective_trade_cost_bps_accepts_custom_fee():
    assert broker_costs.effective_trade_cost_bps(1000, fee_usd=2.0) == pytest.approx(20.0)


def test_effective_trade_cost_bps_rejects_non_positive_position():
    with pytest.raises(ValueError):
        broker_costs.effective_trade_cost_bps(0)
    with pytest.raises(ValueError):
        broker_costs.effective_trade_cost_bps(-100)


def test_position_size_usd_splits_capital_equally():
    assert broker_costs.position_size_usd(10000, 20) == pytest.approx(500.0)


def test_position_size_usd_rejects_invalid_inputs():
    with pytest.raises(ValueError):
        broker_costs.position_size_usd(0, 20)
    with pytest.raises(ValueError):
        broker_costs.position_size_usd(10000, 0)


def test_deposit_fx_costs_are_higher_than_trade_costs_at_typical_position_sizes():
    # El coste de depositar (tarjeta o transferencia) no debe confundirse ni
    # usarse como sustituto del coste de operar en el backtest: son de
    # magnitud distinta y de naturaleza distinta (evento único vs recurrente).
    typical_trade_cost_pct = broker_costs.effective_trade_cost_bps(600) / 100
    assert typical_trade_cost_pct < broker_costs.DEPOSIT_FX_PCT_BANK_TRANSFER
    assert typical_trade_cost_pct < broker_costs.DEPOSIT_FX_PCT_CARD
