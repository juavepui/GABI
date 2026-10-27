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


def _finite(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(number) or number in (float("inf"), float("-inf")) else number


def changes(entry: dict, current: dict) -> dict:
    """What moved since the thesis (#186): price, score and checklist, against what was captured then.

    The score change is only given when both scores come from the same model; a missing side gives None.
    """
    price, entry_price = _finite(current.get("price")), _finite(entry.get("entry_price"))
    score, entry_score = _finite(current.get("score")), _finite(entry.get("entry_score"))
    same_model = entry.get("model_id") is not None and entry.get("model_id") == current.get("model_id")
    passed, evaluated = current.get("checklist_passed"), current.get("checklist_evaluated")
    entry_passed, entry_evaluated = entry.get("entry_checklist_passed"), entry.get("entry_checklist_evaluated")
    return {
        "price": price, "price_date": current.get("price_date"), "entry_price": entry_price,
        "price_return": price / entry_price - 1 if price is not None and entry_price else None,
        "score": score, "entry_score": entry_score, "same_model": same_model,
        "score_change": score - entry_score if same_model and score is not None and entry_score is not None
        else None,
        "checklist_passed": passed, "checklist_evaluated": evaluated,
        "entry_checklist_passed": entry_passed, "entry_checklist_evaluated": entry_evaluated,
        "checklist_change": passed - entry_passed if passed is not None and entry_passed is not None else None,
    }
