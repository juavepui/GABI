"""Identity and visible status of a versioned operating model (ADR 0008)."""

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from types import MappingProxyType

from gabi.domain.market import engine_fundamentals, revenue_growth, sec_metrics_v2
from gabi.domain.market.input_checks import VERSION as INPUT_CHECKS_VERSION
from gabi.domain.market.model_policy import FROZEN_WEIGHTS, model_status, weights_match_frozen
from gabi.domain.market.technicals import TechnicalParameters

BLOCKS = frozenset(FROZEN_WEIGHTS)
# SEC metrics a version scores with: V1 (`sec_facts`, stored in edgar_metrics), V2.1 (#245: ROIC from
# sec_metrics_v2) or V2.2 (#339: V2.1 plus the revenue growth of revenue-growth-v1).
SEC_METRICS_V1 = "sec-metrics-v1"
SEC_METRICS_V2_2 = revenue_growth.METRICS_VERSION
# #347: the eight company metrics as the tested historical engine computes them (engine-fundamentals-v1).
SEC_ENGINE_V1 = engine_fundamentals.METRICS_VERSION
SEC_METRICS_VERSIONS = frozenset({SEC_METRICS_V1, sec_metrics_v2.VERSION, SEC_METRICS_V2_2, SEC_ENGINE_V1})


@dataclass(frozen=True)
class ModelVersion:
    """Pesos, parámetros técnicos, benchmark, tipo libre de riesgo y métricas SEC de una versión.

    `sealed_hypothesis` solo es True para la hipótesis congelada: su estado sigue
    las reglas de `model_policy`. Una versión nueva empieza sin evidencia y se
    muestra EXPERIMENTAL por sí misma, no por desviarse de otra."""

    model_id: str
    label: str
    weights: Mapping[str, float]
    technical: TechnicalParameters
    benchmark_symbol: str
    risk_free_rate: float
    sealed_hypothesis: bool = False
    metrics_version: str = SEC_METRICS_V1
    # Plausibility policy applied before scoring (#295); None scores every value as it comes.
    input_checks: str | None = None

    def __post_init__(self) -> None:
        if not self.model_id or self.model_id == "EXPERIMENTAL" or not self.label or not self.benchmark_symbol:
            raise ValueError("A model version needs an id, a label and a benchmark")
        values = list(self.weights.values())
        if set(self.weights) != BLOCKS or any(not isfinite(value) or not 0 <= value <= 1 for value in values) \
                or abs(sum(values) - 1) > 1e-6:
            raise ValueError("Weights must be four fractions that sum to 1")
        if not isfinite(self.risk_free_rate):
            raise ValueError("The risk-free rate must be finite")
        if self.metrics_version not in SEC_METRICS_VERSIONS:
            raise ValueError(f"Unknown SEC metrics version: {self.metrics_version}")
        if self.sealed_hypothesis and self.metrics_version != SEC_METRICS_V1:
            raise ValueError("The sealed hypothesis scores with the SEC metrics V1")
        if self.input_checks not in (None, INPUT_CHECKS_VERSION):
            raise ValueError(f"Unknown input checks: {self.input_checks}")
        if self.sealed_hypothesis and self.input_checks is not None:
            raise ValueError("The sealed hypothesis scores every value as it comes")
        if min(vars(self.technical).values()) <= 0:
            raise ValueError("Technical windows must be positive")
        object.__setattr__(self, "weights", MappingProxyType(dict(self.weights)))


def matches(version: ModelVersion, weights: dict) -> bool:
    return weights_match_frozen(weights, frozen_weights=version.weights)


def status(version: ModelVersion, weights: dict, *, live_forward_active: bool = False) -> str:
    if not version.sealed_hypothesis:
        return "EXPERIMENTAL"
    return model_status(weights, live_forward_active=live_forward_active, frozen_weights=version.weights)
