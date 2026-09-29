from collections.abc import Callable
from dataclasses import dataclass
from math import isfinite
from typing import Protocol

from gabi.application.errors import QueryError


@dataclass(frozen=True)
class ModelPolicy:
    frozen_weights: dict[str, float]
    frozen_id: str
    matches: Callable[..., bool]
    status: Callable[..., str]


@dataclass
class LocalModel:
    mode: str
    saved_weights: dict[str, float]
    blind_id: int | None = None
    weak_tracking: bool = False


@dataclass
class ModelState:
    mode: str
    model_id: str
    status: str
    weights: dict[str, float]
    matches_frozen: bool
    live_forward_source: str | None
    blind_validation_id: int | None
    independent_advantage_demonstrated: bool = False


class ModelReader(Protocol):
    def local_model(self) -> LocalModel: ...


class WeightWriter(Protocol):
    def save_weights(self, weights: dict[str, float]) -> None: ...


class ModelQueries:
    def __init__(self, reader: ModelReader, policy: ModelPolicy):
        self.reader, self.policy = reader, policy

    def model(self, override: dict[str, float] | None = None) -> ModelState:
        local = self.reader.local_model()
        if override is not None and local.mode != "RESEARCH":
            raise QueryError("research_required", "Los pesos alternativos requieren el modo Research local.", 403)
        weights = override if override is not None else (
            self.policy.frozen_weights if local.mode == "INVESTOR" else local.saved_weights)
        if set(weights) != set(self.policy.frozen_weights) or any(
            not isfinite(value) or value < 0 or value > 1 for value in weights.values()
        ) or abs(sum(weights.values()) - 1) > 1e-6:
            raise QueryError("invalid_weights", "Los cuatro pesos deben ser fracciones cuya suma sea 1.", 422)
        matches = self.policy.matches(weights)
        source = ("blind_validation" if local.blind_id is not None else
                  "research_lab" if local.weak_tracking else None) if matches else None
        return ModelState(local.mode, self.policy.frozen_id if matches else "EXPERIMENTAL",
                          self.policy.status(weights, live_forward_active=source is not None), dict(weights), matches,
                          source, local.blind_id if matches else None)


class ModelCommands:
    def __init__(self, queries: ModelQueries, writer: WeightWriter):
        self.queries, self.writer = queries, writer

    def save_weights(self, weights: dict[str, float]) -> ModelState:
        self.queries.model(weights)  # validates four finite fractions and Research mode before any write
        self.writer.save_weights(weights)
        return self.queries.model()
