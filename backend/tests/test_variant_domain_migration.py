"""The original declared protocol and financial windows, without executing a backtest."""

import json
from pathlib import Path

import pandas as pd
import pytest
from test_variant_validation import _fake_result

from gabi.application.research.variant_validation import run_validation
from gabi.domain.research.variant_validation import DEFAULT_END, DEFAULT_START, VariantSpec, window_metrics

REFERENCE = json.loads((Path(__file__).parent / "fixtures/variant_validation_migration.json").read_text(encoding="utf-8"))


def test_full_report_matches_original_without_io(monkeypatch):
    calls = []

    def runner(start, end, **params):
        calls.append((start, end, params))
        return _fake_result(start, end, **params)

    # Calendar data is initialized before prohibiting file access.
    _fake_result(DEFAULT_START, DEFAULT_END)

    def forbidden(*args, **kwargs):
        raise AssertionError("implicit IO")

    monkeypatch.setattr(Path, "open", forbidden)
    result = run_validation([VariantSpec("hurdle_5", {"rotation_hurdle_points": 5})], runner=runner)
    for key in ("protocol", "variants_declared", "future"):
        assert result[key] == REFERENCE[key]
    pd.testing.assert_frame_equal(result["report"], pd.DataFrame(REFERENCE["report"]),
                                  check_exact=False, rtol=1e-12, atol=1e-14)
    common = {"months": 3, "top_n": 20, "max_symbols": None, "mode": "validation"}
    assert calls == [(DEFAULT_START, DEFAULT_END, common),
                     (DEFAULT_START, DEFAULT_END, common | {"rotation_hurdle_points": 5})]


def test_window_does_not_mutate_input():
    result = _fake_result(DEFAULT_START, DEFAULT_END)
    originals = {key: value.copy(deep=True) for key, value in result.items() if isinstance(value, (pd.Series, pd.DataFrame))}
    window_metrics(result, DEFAULT_START, "2021-01-02")
    for key, before in originals.items():
        if isinstance(before, pd.Series):
            pd.testing.assert_series_equal(result[key], before)
        else:
            pd.testing.assert_frame_equal(result[key], before)


@pytest.mark.parametrize("variants", [[], [VariantSpec("control_composite")], [VariantSpec("x"), VariantSpec("x")]])
def test_invalid_protocol_never_calls_runner(variants):
    def forbidden(*args, **kwargs):
        raise AssertionError("invalid protocol reached runner")

    with pytest.raises(ValueError):
        run_validation(variants, runner=forbidden)


def test_runner_is_required():
    with pytest.raises(TypeError):
        run_validation([VariantSpec("x")])
