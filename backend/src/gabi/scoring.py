"""Legacy compatibility for ``gabi.domain.market.scoring``."""

import gabi.domain.market.scoring as _implementation
from gabi.domain.market.scoring import pd

_percentile = _implementation._percentile
_percentile_within_sector = _implementation._percentile_within_sector
add_percentile_columns = _implementation.add_percentile_columns
compute_block_score = _implementation.compute_block_score
_weighted_row_mean = _implementation._weighted_row_mean
explain_row = _implementation.explain_row
VALUE_METRICS_LOWER_BETTER = _implementation.VALUE_METRICS_LOWER_BETTER
QUALITY_METRICS_HIGHER_BETTER = _implementation.QUALITY_METRICS_HIGHER_BETTER
MOMENTUM_METRICS_HIGHER_BETTER = _implementation.MOMENTUM_METRICS_HIGHER_BETTER
RISK_METRICS_LOWER_BETTER = _implementation.RISK_METRICS_LOWER_BETTER
RISK_METRICS_HIGHER_BETTER = _implementation.RISK_METRICS_HIGHER_BETTER
DEFAULT_WEIGHTS = _implementation.DEFAULT_WEIGHTS
DEFAULT_MIN_SECTOR_GROUP = _implementation.DEFAULT_MIN_SECTOR_GROUP
MIN_SCORE_COVERAGE = _implementation.MIN_SCORE_COVERAGE
SCORE_METRICS = _implementation.SCORE_METRICS


def _parameters() -> _implementation.ScoringParameters:
    return _implementation.ScoringParameters(
        tuple(VALUE_METRICS_LOWER_BETTER), tuple(QUALITY_METRICS_HIGHER_BETTER),
        tuple(MOMENTUM_METRICS_HIGHER_BETTER), tuple(RISK_METRICS_LOWER_BETTER),
        tuple(RISK_METRICS_HIGHER_BETTER), tuple((key, tuple(values)) for key, values in SCORE_METRICS.items()),
        tuple(DEFAULT_WEIGHTS.items()), MIN_SCORE_COVERAGE, DEFAULT_MIN_SECTOR_GROUP,
    )


def build_scores(df: pd.DataFrame, weights: dict = None) -> pd.DataFrame:
    return _implementation.build_scores(df, weights, parameters=_parameters())


def compute_confidence(df: pd.DataFrame, weights: dict = None) -> pd.Series:
    return _implementation.compute_confidence(df, weights, parameters=_parameters())
