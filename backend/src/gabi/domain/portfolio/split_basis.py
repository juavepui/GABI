"""Shared conversion from today's split-adjusted price base to a dated share base."""

import math

import pandas as pd


def split_factor(index: pd.DatetimeIndex, splits: pd.Series) -> pd.Series:
    """Product of the split ratios after each session (new shares per old)."""
    factor = pd.Series(1.0, index=index)
    for day, ratio in splits.items():
        if ratio and math.isfinite(ratio) and ratio > 0:
            factor[factor.index < pd.Timestamp(day)] *= float(ratio)
    return factor
