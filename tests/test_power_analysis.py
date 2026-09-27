"""#39: power formulas."""

import math

from gabi import power_analysis as pa


def test_quarters_needed_matches_the_closed_form_and_inverts_the_detectable_effect():
    n = pa.quarters_needed(0.01, 0.04)
    assert math.isclose(n, ((1.6448536 + 0.8416212) * 4) ** 2, rel_tol=1e-6)
    assert math.isclose(pa.minimum_detectable(0.04, n), 0.01, rel_tol=1e-9)
    assert math.isclose(pa.power_at(0.01, 0.04, n), 0.80, rel_tol=1e-6)
    assert pa.quarters_needed(0.0, 0.04) == math.inf
