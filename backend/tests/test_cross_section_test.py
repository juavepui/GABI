"""#40: Fama-MacBeth slope and the frozen specification."""

import numpy as np
import pandas as pd

from gabi import cross_section_test as cs


def test_fama_macbeth_slope_recovers_a_rank_effect_with_sector_and_size_controls():
    rng = np.random.default_rng(1)
    n = 200
    score = rng.normal(size=n)
    frame = pd.DataFrame({"composite_score": score, "sector": rng.choice(["A", "B", "C"], n),
                          "market_cap": np.exp(rng.normal(22, 1, n))})
    frame["retorno"] = 0.05 * frame.composite_score.rank(pct=True) + rng.normal(0, 0.001, n)
    assert abs(cs.fama_macbeth_slope(frame) - 0.05) < 0.005
    assert cs.fama_macbeth_slope(frame.head(10)) is None


def test_specification_is_frozen():
    assert cs.SPEC["primary"]["alpha"] == 0.05 and len(cs.spec_hash()) == 64
    assert "no confirmatorio" in cs.SPEC["descriptive"][0]
