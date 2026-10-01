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


class CompanyEvent(BaseModel):
    event_type: Literal["earnings", "ex_dividend", "dividend_payment"]
    event_date: str
    range_end: str | None
    is_estimate: bool
    days_until: int
    source: str


class EarningsSurprise(BaseModel):
    earnings_date: str
    eps_estimate: float | None
    eps_reported: float | None
    surprise_pct: float | None
    price_reaction_pct: float | None


class ConsensusEstimate(BaseModel):
    captured_at: str
    eps_avg: float | None
    eps_low: float | None
    eps_high: float | None
    eps_analysts: int | None
    eps_dispersion_pct: float | None
    revised_up_30d: int | None
    revised_down_30d: int | None
    source: str


class CompanyResearchResponse(BaseModel):
    symbol: str
    events: list[CompanyEvent]
    surprises: list[EarningsSurprise]
    estimate: ConsensusEstimate | None
    revision_90d: dict[str, Any] | None


class FilingRef(BaseModel):
    filed_date: str | None
    period_end: str | None
    url: str | None


class FilingChange(BaseModel):
    metric: str
    previous_value: float | None
    current_value: float | None
    abs_change: float | None
    pct_change: float | None
    severity: str
    direction: str


class FilingComparison(BaseModel):
    form: str
    reason: str | None
    current: FilingRef | None
    previous: FilingRef | None
    rows: list[FilingChange]


class CompanyFilingChanges(BaseModel):
    symbol: str
    results: list[FilingComparison]
