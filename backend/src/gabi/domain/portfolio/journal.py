"""Expected outcome of a written investment thesis."""

import pandas as pd


def compute_expected_value(entry_price, bear_price, base_price, bull_price, bear_prob, base_prob, bull_prob):
    prices = [bear_price, base_price, bull_price]
    probs = [bear_prob, base_prob, bull_prob]
    if not entry_price or entry_price <= 0:
        return None
    if any(p is None or (isinstance(p, float) and pd.isna(p)) for p in prices):
        return None
    if any(p is None or (isinstance(p, float) and pd.isna(p)) for p in probs):
        return None
    total_prob = sum(probs)
    if total_prob <= 0:
        return None
    weights = [p / total_prob for p in probs]
    expected_price = sum(pr * w for pr, w in zip(prices, weights))
    return {
        "expected_price": expected_price,
        "expected_return_pct": (expected_price / entry_price - 1) * 100,
        "probs_summed_to_100": abs(total_prob - 100) < 0.01,
    }
