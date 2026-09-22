import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gabi import simple_portfolio as sp


def _make_df(rows: list) -> pd.DataFrame:
    """rows: [(symbol, name, composite_score, score_coverage), ...]"""
    return pd.DataFrame(
        [{"name": name, "composite_score": score, "score_coverage": coverage} for _, name, score, coverage in rows],
        index=[symbol for symbol, *_ in rows],
    ).rename_axis("symbol")


def test_eligible_candidates_filters_low_coverage_and_missing_score():
    df = _make_df([
        ("A", "Empresa A", 80, 0.9),
        ("B", "Empresa B", 70, 0.5),  # cobertura por debajo del umbral
        ("C", "Empresa C", None, 0.9),  # sin score
    ])
    eligible = sp.eligible_candidates(df)
    assert list(eligible.index) == ["A"]


def test_eligible_candidates_empty_input_returns_empty():
    assert sp.eligible_candidates(pd.DataFrame()).empty


def test_target_portfolio_picks_top_n_by_score_and_weights_equally():
    df = _make_df([
        ("A", "Empresa A", 90, 0.9), ("B", "Empresa B", 80, 0.9),
        ("C", "Empresa C", 70, 0.9), ("D", "Empresa D", 60, 0.9),
    ])
    target = sp.target_portfolio(df, n_positions=2)
    assert list(target.index) == ["A", "B"]  # las dos mejores por score
    assert (target["weight_pct"] == 50.0).all()


def test_target_portfolio_weight_reflects_actual_count_not_requested_n():
    """Si hay menos candidatas elegibles que las pedidas, el peso se reparte
    entre las que de verdad hay -- no se infla el resto para aparentar N."""
    df = _make_df([("A", "Empresa A", 90, 0.9), ("B", "Empresa B", 80, 0.9)])
    target = sp.target_portfolio(df, n_positions=20)
    assert len(target) == 2
    assert (target["weight_pct"] == 50.0).all()


def test_target_portfolio_empty_when_nothing_eligible():
    df = _make_df([("A", "Empresa A", None, 0.9)])
    target = sp.target_portfolio(df, n_positions=20)
    assert target.empty


def test_target_portfolio_rejects_zero_or_negative_n_gracefully():
    df = _make_df([("A", "Empresa A", 90, 0.9)])
    assert sp.target_portfolio(df, n_positions=0).empty


def test_parse_holdings_parses_symbol_and_amount():
    holdings = sp.parse_holdings("AAPL,300\nMSFT,200.5")
    assert holdings == {"AAPL": 300.0, "MSFT": 200.5}


def test_parse_holdings_ignores_blank_lines_and_uppercases_symbol():
    holdings = sp.parse_holdings("\naapl,100\n\n")
    assert holdings == {"AAPL": 100.0}


def test_parse_holdings_aggregates_duplicate_symbols():
    holdings = sp.parse_holdings("AAPL,100\nAAPL,50")
    assert holdings == {"AAPL": 150.0}


def test_parse_holdings_empty_text_returns_empty_dict():
    assert sp.parse_holdings("") == {}
    assert sp.parse_holdings("   \n  ") == {}


@pytest.mark.parametrize("bad_line", ["AAPL", "AAPL,100,200", ",100", "AAPL,notanumber"])
def test_parse_holdings_rejects_invalid_format(bad_line):
    with pytest.raises(ValueError):
        sp.parse_holdings(bad_line)


def _target(rows):
    """rows: [(symbol, name), ...] -- cartera objetivo equiponderada de prueba."""
    df = pd.DataFrame([{"name": name} for _, name in rows], index=[s for s, _ in rows]).rename_axis("symbol")
    df["weight_pct"] = 100 / len(df)
    return df


def test_allocate_new_capital_prioritizes_most_underweight_position():
    target = _target([("A", "Empresa A"), ("B", "Empresa B")])
    # Objetivo = (40 ya invertidos + 100 nuevos) / 2 posiciones = 70 cada una.
    result = sp.allocate_new_capital(target, {"B": 40.0}, new_capital=100.0)
    symbols = [a["symbol"] for a in result["allocations"]]
    assert symbols[0] == "A"  # mas infraponderada (0 vs objetivo 70) va primero
    assert result["allocations"][0]["amount"] == pytest.approx(70.0)
    assert result["allocations"][1]["symbol"] == "B"
    assert result["allocations"][1]["amount"] == pytest.approx(30.0)  # 70 objetivo - 40 ya invertido
    assert result["remaining"] == pytest.approx(0.0)  # 100 = 70 + 30, todo el capital nuevo se coloca


def test_allocate_new_capital_stops_when_capital_runs_out_before_covering_all_gaps():
    target = _target([("A", "Empresa A"), ("B", "Empresa B"), ("C", "Empresa C")])
    result = sp.allocate_new_capital(target, {}, new_capital=10.0)
    # Objetivo por posicion = 10/3 -- las tres empiezan en 0, mismo hueco: reparte hasta agotar.
    assert sum(a["amount"] for a in result["allocations"]) == pytest.approx(10.0)
    assert result["remaining"] == pytest.approx(0.0)


def test_allocate_new_capital_no_gaps_when_already_balanced_and_no_new_capital():
    """El objetivo se calcula sobre el total FUTURO (lo ya invertido + el
    capital nuevo) -- con capital nuevo > 0 casi siempre hay hueco donde
    meterlo (el objetivo sube con el total), así que el caso "sin huecos" de
    verdad solo se da sin capital nuevo y ya equilibrado."""
    target = _target([("A", "Empresa A"), ("B", "Empresa B")])
    result = sp.allocate_new_capital(target, {"A": 500.0, "B": 500.0}, new_capital=0.0)
    assert result["allocations"] == []
    assert result["remaining"] == pytest.approx(0.0)


def test_allocate_new_capital_flags_holdings_outside_target_without_recommending_sale():
    target = _target([("A", "Empresa A")])
    result = sp.allocate_new_capital(target, {"A": 0.0, "ZZZZ": 500.0}, new_capital=100.0)
    assert result["outside_target"] == ["ZZZZ"]


def test_allocate_new_capital_rejects_negative_capital():
    target = _target([("A", "Empresa A")])
    with pytest.raises(ValueError):
        sp.allocate_new_capital(target, {}, new_capital=-1.0)


def test_allocate_new_capital_empty_target_returns_no_allocations():
    result = sp.allocate_new_capital(pd.DataFrame(), {"A": 100.0}, new_capital=50.0)
    assert result == {"allocations": [], "remaining": 50.0, "outside_target": ["A"]}


def test_allocate_new_capital_zero_new_capital_still_reports_outside_target():
    target = _target([("A", "Empresa A")])
    result = sp.allocate_new_capital(target, {"ZZZZ": 100.0}, new_capital=0.0)
    assert result["allocations"] == []
    assert result["outside_target"] == ["ZZZZ"]
