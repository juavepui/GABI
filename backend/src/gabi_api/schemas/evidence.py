"""Evidence and ranking fragility of the current ranking; categories, never probabilities."""

from typing import Any, Literal

from pydantic import BaseModel

Level = Literal["BAJA", "MEDIA", "ALTA"]


class EvidenceRow(BaseModel):
    symbol: str
    score: float | None
    weighted_data_coverage: float | None
    confidence_level: Level
    top20_persistence: float | None
    validated_score_fraction: float | None


class EvidenceTop(BaseModel):
    revision: str
    mode: Literal["INVESTOR", "RESEARCH"]
    weights: dict[str, float]
    available: bool
    rows: list[EvidenceRow]


class SicStability(BaseModel):
    group: str
    name: str | None = None
    ic_mean: float | None = None
    n_periods: int | None = None
    status: str | None = None


class EvidenceFactor(BaseModel):
    metric: str
    family: str
    percentile: float
    supports_candidate: bool
    effective_weight: float
    contribution_points: float
    statistically_supported: bool
    mean_ic: float | None
    p_holm: float | None
    sic_division_stability: list[SicStability]


class CompanyEvidence(BaseModel):
    symbol: str
    revision: str
    mode: Literal["INVESTOR", "RESEARCH"]
    confidence_level: Level
    score: float | None
    score_coverage: float | None
    weighted_data_coverage: float | None
    reasons_for: list[str]
    reasons_against: list[str]
    factors: list[EvidenceFactor]
    validated_score_fraction: float | None
    top20_persistence: float | None
    collection_stage: str
    evidence_stage: str
    rules_version: str
    interpretation: str
    research_details: dict[str, Any] | None


class StabilitySummary(BaseModel):
    eligible: int
    excluded: int
    perturbations: int
    omitted_infeasible: int
    stability_score: float | None
    sectors_complete: bool
    interpretation: str


class RankingStability(BaseModel):
    revision: str
    mode: Literal["INVESTOR", "RESEARCH"]
    weights: dict[str, float]
    available: bool
    message: str | None
    summary: StabilitySummary | None
    companies: list[dict[str, str | float | int | None]]
    metrics: list[dict[str, str | float | int | None]]
    perturbations: list[dict[str, str | float | int | None]]


class BlockCoverage(BaseModel):
    block: str
    complete: float
    any: float
    none: float
    n_metrics: int


class RankingCoverage(BaseModel):
    revision: str
    threshold: float
    universe: int
    blocks: list[BlockCoverage]
    warnings: list[str]
