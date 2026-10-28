"""Identity and visible status of a versioned operating model (ADR 0008)."""

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from types import MappingProxyType

from gabi.domain.market.model_policy import FROZEN_WEIGHTS, model_status, weights_match_frozen
from gabi.domain.market.technicals import TechnicalParameters

BLOCKS = frozenset(FROZEN_WEIGHTS)


@dataclass(frozen=True)
class ModelVersion:
    """Pesos, parámetros técnicos, benchmark y tipo libre de riesgo de una versión.

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

    def __post_init__(self) -> None:
        if not self.model_id or self.model_id == "EXPERIMENTAL" or not self.label or not self.benchmark_symbol:
            raise ValueError("A model version needs an id, a label and a benchmark")
        values = list(self.weights.values())
        if set(self.weights) != BLOCKS or any(not isfinite(value) or not 0 <= value <= 1 for value in values) \
                or abs(sum(values) - 1) > 1e-6:
            raise ValueError("Weights must be four fractions that sum to 1")
        if not isfinite(self.risk_free_rate):
            raise ValueError("The risk-free rate must be finite")
        if min(vars(self.technical).values()) <= 0:
            raise ValueError("Technical windows must be positive")
        object.__setattr__(self, "weights", MappingProxyType(dict(self.weights)))


def matches(version: ModelVersion, weights: dict) -> bool:
    return weights_match_frozen(weights, frozen_weights=version.weights)


def status(version: ModelVersion, weights: dict, *, live_forward_active: bool = False) -> str:
    if not version.sealed_hypothesis:
        return "EXPERIMENTAL"
    return model_status(weights, live_forward_active=live_forward_active, frozen_weights=version.weights)
