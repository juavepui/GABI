from functools import partial

import gabi.domain.market.scoring as scoring
from gabi import app_mode, config, events_calendar
from gabi.application.administration.model import ModelPolicy
from gabi.application.market.ranking import Calculators
from gabi.domain.market.fundamentals import compute_fundamental_metrics
from gabi.domain.market.risk import compute_risk_metrics
from gabi.domain.market.technicals import TechnicalParameters, compute_technicals


def calculators() -> Calculators:
    parameters = TechnicalParameters(config.SMA_SHORT, config.SMA_LONG, config.RSI_PERIOD,
                                     config.MOMENTUM_SHORT_DAYS, config.MOMENTUM_LONG_DAYS)
    return Calculators(compute_fundamental_metrics, partial(compute_technicals, parameters=parameters),
                       compute_risk_metrics, events_calendar.parse_corporate_events,
                       scoring.build_scores, scoring.compute_confidence)


def model_policy() -> ModelPolicy:
    return ModelPolicy(dict(app_mode.FROZEN_WEIGHTS), app_mode.FROZEN_MODEL_ID,
                       app_mode.weights_match_frozen, app_mode.model_status)


def defaults() -> tuple[str, float]:
    return config.BENCHMARK_SYMBOL, config.RISK_FREE_RATE


def metric_blocks() -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Every metric of each block (as the old Aprender page listed them) and the 13 that score."""
    blocks = {"value": list(scoring.VALUE_METRICS_LOWER_BETTER),
              "quality": list(scoring.QUALITY_METRICS_HIGHER_BETTER),
              "momentum": list(scoring.MOMENTUM_METRICS_HIGHER_BETTER),
              "risk": list(scoring.RISK_METRICS_LOWER_BETTER) + list(scoring.RISK_METRICS_HIGHER_BETTER)}
    return blocks, {block: list(keys) for block, keys in scoring.SCORE_METRICS.items()}


def metric_directions() -> dict[str, str]:
    """«higher» or «lower» is better, as scoring orders each metric; the scores themselves are higher-better."""
    from gabi.domain.market.comparison import SCORES

    directions = dict.fromkeys(SCORES, "higher")
    directions |= dict.fromkeys(scoring.VALUE_METRICS_LOWER_BETTER + scoring.RISK_METRICS_LOWER_BETTER, "lower")
    directions |= dict.fromkeys(scoring.QUALITY_METRICS_HIGHER_BETTER + scoring.MOMENTUM_METRICS_HIGHER_BETTER
                                + scoring.RISK_METRICS_HIGHER_BETTER, "higher")
    return directions
