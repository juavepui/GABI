import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gabi import tax_drag as td

# --- progressive_tax: límites exactos de tramo, verificados a mano ---

@pytest.mark.parametrize("gain,expected", [
    (0, 0.0),
    (-100, 0.0),
    (5_000, 5_000 * 0.19),
    (6_000, 6_000 * 0.19),
    (10_000, 6_000 * 0.19 + 4_000 * 0.21),
    (50_000, 6_000 * 0.19 + 44_000 * 0.21),
    (60_000, 6_000 * 0.19 + 44_000 * 0.21 + 10_000 * 0.23),
    (200_000, 6_000 * 0.19 + 44_000 * 0.21 + 150_000 * 0.23),
    (250_000, 6_000 * 0.19 + 44_000 * 0.21 + 150_000 * 0.23 + 50_000 * 0.27),
    (300_000, 6_000 * 0.19 + 44_000 * 0.21 + 150_000 * 0.23 + 100_000 * 0.27),
    (400_000, 6_000 * 0.19 + 44_000 * 0.21 + 150_000 * 0.23 + 100_000 * 0.27 + 100_000 * 0.28),
])
def test_progressive_tax_matches_hand_computed_brackets(gain, expected):
    assert td.progressive_tax(gain) == pytest.approx(expected)


def _periods(rows):
    """rows: [(fecha, retorno, turnover_pct), ...] -- turnover_pct puede ser None."""
    return pd.DataFrame(rows, columns=["fecha", "retorno", "turnover_pct"])


def test_simulate_tax_drag_zero_turnover_defers_all_tax():
    periods = _periods([
        ("2024-01-02", 0.10, 0.0), ("2024-04-02", 0.05, 0.0),
        ("2024-07-02", -0.03, 0.0), ("2024-10-02", 0.08, 0.0),
    ])
    result = td.simulate_tax_drag(periods, initial_capital=100.0)
    assert result["total_tax_paid"] == pytest.approx(0.0)
    assert result["final_value_aftertax"] == pytest.approx(result["final_value_pretax"])
    assert result["aftertax_return"] == pytest.approx(result["pretax_return"])


def test_simulate_tax_drag_realizes_gain_on_full_turnover_within_same_year():
    # Periodo 1 (primero de la serie, sin cartera previa que rotar): no realiza nada.
    # Periodo 2, mismo año, turnover 100%: realiza toda la plusvalía acumulada hasta ahi.
    periods = _periods([
        ("2024-01-02", 0.10, None),
        ("2024-04-02", 0.10, 100.0),
    ])
    result = td.simulate_tax_drag(periods, initial_capital=100.0)
    # value tras periodo1=110 (sin realizar), tras periodo2=121; plusvalia realizada=121-100=21.
    assert result["final_value_pretax"] == pytest.approx(121.0)
    expected_tax = td.progressive_tax(21.0)
    assert result["total_tax_paid"] == pytest.approx(expected_tax)
    assert result["final_value_aftertax"] == pytest.approx(121.0 - expected_tax)
    assert result["tax_drag_pct_points"] > 0


def test_simulate_tax_drag_nets_losses_against_gains_within_same_year():
    periods = _periods([
        ("2024-01-02", 0.20, None),    # 100 -> 120, sin realizar (primer periodo)
        ("2024-04-02", -0.30, 100.0),  # 120 -> 84; realiza perdida de 84-100=-16
        ("2024-07-02", 0.20, 100.0),   # 84 -> 100.8; realiza ganancia de 100.8-84=16.8
    ])
    result = td.simulate_tax_drag(periods, initial_capital=100.0)
    year = result["tax_by_year"][2024]
    assert year["realized_net"] == pytest.approx(-16.0 + 16.8)
    assert year["tax"] == pytest.approx(td.progressive_tax(0.8))
    # Sin compensar perdidas, se habria pagado sobre 16.8 en vez de sobre 0.8 -- mucho mas.
    assert year["tax"] < td.progressive_tax(16.8)


def test_simulate_tax_drag_carries_forward_losses_across_years():
    periods = _periods([
        ("2020-01-02", 0.0, None),      # ancla el coste base, sin cambios
        ("2021-06-02", -0.50, 100.0),   # 100 -> 50; realiza perdida de -50 en 2021
        ("2022-06-02", 0.60, 100.0),    # 50 -> 80; realiza ganancia de +30 en 2022
        ("2023-06-02", 0.3125, 100.0),  # 80 -> 105; realiza ganancia de +25 en 2023
    ])
    result = td.simulate_tax_drag(periods, initial_capital=100.0)
    by_year = result["tax_by_year"]
    assert by_year[2021]["tax"] == pytest.approx(0.0)  # perdida neta: nada que pagar, se arrastra
    assert by_year[2022]["tax"] == pytest.approx(0.0)  # +30 compensado con el arrastre de -50 (-20 neto)
    # 2023: +25 compensado con el arrastre restante de -20 = 5 neto, tributa sobre eso.
    assert by_year[2023]["realized_net"] == pytest.approx(5.0)
    assert by_year[2023]["tax"] == pytest.approx(td.progressive_tax(5.0))
    assert result["total_tax_paid"] == pytest.approx(td.progressive_tax(5.0))


def test_simulate_tax_drag_rejects_empty_periods():
    with pytest.raises(ValueError):
        td.simulate_tax_drag(pd.DataFrame(columns=["fecha", "retorno", "turnover_pct"]))


def test_simulate_tax_drag_rejects_non_positive_initial_capital():
    periods = _periods([("2024-01-02", 0.1, None)])
    with pytest.raises(ValueError):
        td.simulate_tax_drag(periods, initial_capital=0.0)


def test_simulate_tax_drag_rejects_missing_columns():
    with pytest.raises(ValueError):
        td.simulate_tax_drag(pd.DataFrame({"fecha": ["2024-01-02"], "retorno": [0.1]}))


def test_simulate_tax_drag_rejects_turnover_out_of_range():
    periods = _periods([("2024-01-02", 0.1, None), ("2024-04-02", 0.1, 150.0)])
    with pytest.raises(ValueError):
        td.simulate_tax_drag(periods)


def test_zero_turnover_periods_builds_expected_frame():
    periods = pd.DataFrame({"fecha": ["2024-01-02", "2024-04-02"], "spy": [0.05, -0.02]})
    zt = td.zero_turnover_periods(periods, "spy")
    assert list(zt["retorno"]) == [0.05, -0.02]
    assert (zt["turnover_pct"] == 0.0).all()


def test_zero_turnover_periods_rejects_missing_column():
    with pytest.raises(ValueError):
        td.zero_turnover_periods(pd.DataFrame({"fecha": ["2024-01-02"]}), "spy")


def test_high_turnover_strategy_pays_more_tax_than_buy_and_hold_on_same_underlying_return():
    """La comprobación de fondo del issue: mismo retorno subyacente, pero el
    turnover alto realiza plusvalia antes -- el buy-and-hold la difiere."""
    dates = ["2024-01-02", "2024-04-02", "2024-07-02", "2024-10-02"]
    rets = [0.08, 0.05, -0.02, 0.06]
    high_turnover = _periods(list(zip(dates, rets, [None, 100.0, 100.0, 100.0], strict=True)))
    buy_and_hold = _periods(list(zip(dates, rets, [0.0, 0.0, 0.0, 0.0], strict=True)))

    result_high = td.simulate_tax_drag(high_turnover, initial_capital=100.0)
    result_hold = td.simulate_tax_drag(buy_and_hold, initial_capital=100.0)

    assert result_high["final_value_pretax"] == pytest.approx(result_hold["final_value_pretax"])
    assert result_high["total_tax_paid"] > result_hold["total_tax_paid"]
    assert result_high["final_value_aftertax"] < result_hold["final_value_aftertax"]
