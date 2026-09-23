import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gabi.rotation_policy import select_with_score_hurdle


def test_zero_hurdle_is_strict_top_n():
    assert select_with_score_hurdle(["C", "D"], ["A", "B", "C"],
                                    {"A": 90, "B": 80, "C": 70}, 2) == ["A", "B"]


def test_hurdle_keeps_previous_position_when_improvement_is_too_small():
    result = select_with_score_hurdle(["B", "C"], ["A", "B", "C"],
                                      {"A": 71, "B": 80, "C": 70}, 2, hurdle_points=2)
    assert result == ["B", "C"]


def test_hurdle_replaces_weakest_position_only_above_threshold():
    result = select_with_score_hurdle(["B", "C"], ["A", "B", "C"],
                                      {"A": 85, "B": 80, "C": 70}, 2, hurdle_points=2)
    assert result == ["A", "B"]


def test_hurdle_drops_previous_symbol_that_is_no_longer_eligible():
    result = select_with_score_hurdle(["C"], ["A", "B"],
                                      {"A": 90, "B": 80}, 2, hurdle_points=5)
    assert result == ["A", "B"]


def test_hurdle_validates_arguments():
    with pytest.raises(ValueError):
        select_with_score_hurdle([], ["A"], {"A": 1}, 0)
    with pytest.raises(ValueError):
        select_with_score_hurdle([], ["A"], {"A": 1}, 1, -1)
