from gabi import app_mode, config, events_calendar, metrics, risk, scoring, technicals
from gabi.application.administration.model import ModelPolicy
from gabi.application.market.ranking import Calculators


def calculators() -> Calculators:
    return Calculators(metrics.compute_fundamental_metrics, technicals.compute_technicals,
                       risk.compute_risk_metrics, events_calendar.parse_corporate_events,
                       scoring.build_scores, scoring.compute_confidence)


def model_policy() -> ModelPolicy:
    return ModelPolicy(dict(app_mode.FROZEN_WEIGHTS), app_mode.FROZEN_MODEL_ID,
                       app_mode.weights_match_frozen, app_mode.model_status)


def defaults() -> tuple[str, float]:
    return config.BENCHMARK_SYMBOL, config.RISK_FREE_RATE
