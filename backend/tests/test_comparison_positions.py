"""The comparator colours who wins each metric, from the scoring directions."""

from gabi.domain.market.comparison import positions
from gabi.infrastructure.legacy.market import metric_directions


def test_positions_follow_the_direction_of_each_metric():
    values = {"A": {"pe": 10.0, "roe": 0.2, "x": 1}, "B": {"pe": 20.0, "roe": 0.1, "x": 2},
              "C": {"pe": 15.0, "roe": None, "x": 3}}
    result = positions(values, {"pe": "lower", "roe": "higher"})
    assert result["pe"] == {"A": 1.0, "B": 0.0, "C": 0.5}
    assert result["roe"] == {"A": 1.0, "B": 0.0, "C": None}
    assert "x" not in result


def test_ties_and_single_values_have_no_winner():
    assert positions({"A": {"pe": 5.0}, "B": {"pe": 5.0}}, {"pe": "lower"})["pe"] == {"A": None, "B": None}
    assert positions({"A": {"pe": 5.0}, "B": {"pe": None}}, {"pe": "lower"})["pe"] == {"A": None, "B": None}


def test_directions_come_from_scoring():
    directions = metric_directions()
    assert directions["pe"] == "lower" and directions["volatility"] == "lower"
    assert directions["roe"] == "higher" and directions["max_drawdown"] == "higher"
    assert directions["composite_score"] == "higher" and "price" not in directions
