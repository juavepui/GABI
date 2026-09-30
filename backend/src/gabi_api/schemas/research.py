"""Public research catalog contracts; no operational holdout results."""

from typing import Any, Literal

from pydantic import BaseModel


class Diagnostic(BaseModel):
    family: str
    specification_ref: str | None = None
    result_ref: str | None = None
    classification: str


class ResearchOverview(BaseModel):
    as_of: str
    scope: str
    counts: dict[str, int]
    exhaustive_search_history: bool
    global_error_control_established: bool
    limitations: list[str]
    diagnostics: list[Diagnostic]
    unresolved_groups: list[Any]
    families: list[str]


class SearchTrial(BaseModel):
    id: str
    family: str
    configuration_sha256: str
    specification_ref: str
    result_ref: str | None
    observed_sample: dict[str, Any] | None
    planned_sample: dict[str, Any] | None
    state: str
    decision: str
    failures: list[str] | None
    demonstrated_superiority: bool


class SearchTrials(BaseModel):
    total: int
    offset: int
    items: list[SearchTrial]


class HistoricalRow(BaseModel):
    symbol: str
    name: str | None = None
    sector: str | None = None
    composite_score: float | None = None
    score_coverage: float | None = None
    confidence: float | None = None
    identity_status: str | None = None
    sector_is_approximate: bool | None = None
    price: float | None = None


class HistoricalPreview(BaseModel):
    job_id: str
    as_of: str
    status: str
    independent_advantage_demonstrated: bool
    universe_info: dict[str, Any]
    total: int
    shown: int
    rows: list[HistoricalRow]
    result_sha256: str


class BlindIntegrity(BaseModel):
    ok: bool
    broken_at: str | None
    n_periods: int


class BlindStatus(BaseModel):
    id: int
    name: str
    status: str
    unlock_date: str
    n_periods: int
    next_rebalance_due: str
    days_to_unlock: int
    integrity: BlindIntegrity
    revealed: bool


class BlindStatuses(BaseModel):
    items: list[BlindStatus]


class EstimateCaptureStatus(BaseModel):
    period: Literal["0q"]
    batches_total: int
    batches_eligible: int
    first_eligible: str | None
    last_eligible: str | None
    span_days: int
    batches_needed: int
    span_days_needed: int
    symbols_per_batch_needed: int
    history_threshold_met: bool
    evaluation_status: Literal["not_run"]
    independent_advantage_demonstrated: bool


class EstimateAnalysisRow(BaseModel):
    horizonte: int
    ic_mean: float | None
    ic_std: float | None
    icir: float | None
    pct_ic_positive: float | None
    n_periods: int


class EstimateAnalysisPreview(BaseModel):
    job_id: str
    status: Literal["insufficient_data", "ok"]
    observed_cutoff: str
    period: Literal["0q"]
    horizons_months: list[int]
    batches_available: int
    batches_needed: int
    span_days: int
    span_days_needed: int
    reason: str | None
    summary: list[EstimateAnalysisRow]
    independent_advantage_demonstrated: bool
    result_sha256: str


class FactorSummaryRow(BaseModel):
    factor: str
    horizonte: int
    sector_neutral: bool
    ic_mean: float | None = None
    ic_std: float | None = None
    icir: float | None = None
    pct_ic_positive: float | None = None
    q_spread: float | None = None
    n_periods: int


class FactorTurnoverRow(BaseModel):
    factor: str
    quantil: int
    turnover: float | None = None


class FactorQuantileMean(BaseModel):
    factor: str
    horizonte: int
    quantil: int
    retorno_medio: float | None = None
    retorno_medio_neutral: float | None = None


class FactorSkippedPeriod(BaseModel):
    fecha: str
    motivo: str


class FactorPreview(BaseModel):
    job_id: str
    start: str
    end: str
    months: int
    mode: str
    max_symbols: int | None
    status: str
    independent_advantage_demonstrated: bool
    summary: list[FactorSummaryRow]
    turnover: list[FactorTurnoverRow]
    quantile_means: list[FactorQuantileMean]
    skipped: list[FactorSkippedPeriod]
    skipped_count: int
    result_sha256: str


class PublishedSicWindow(BaseModel):
    period: str
    ic_mean: float | None
    n_periods: int


class PublishedSicDivision(BaseModel):
    division: str
    name: str
    ic_mean: float | None
    icir: float | None
    n_periods: int
    positive_fraction: float | None
    status: str
    windows: list[PublishedSicWindow]


class PublishedFactor(BaseModel):
    metric: str
    ic_mean: float | None
    icir: float | None
    p_holm: float | None
    classification: str
    n_periods: int
    q_spread: float | None
    sic_divisions: list[PublishedSicDivision]


class PublishedSicCoverage(BaseModel):
    date: str
    stratum: str
    n_eligible: int
    n_identity: int
    n_selected_filing: int
    n_classified: int
    classified_fraction: float | None


class PublishedFactors(BaseModel):
    status: Literal["RETROSPECTIVE_DESCRIPTIVE"]
    independent_advantage_demonstrated: bool
    holm_significant_count: int
    factor_zoo_sha256: str
    sic_sha256: str
    n_dates: int
    minimum_pairs: int
    minimum_summary_periods: int
    n_eligible: int
    n_classified: int
    classified_fraction: float | None
    factors: list[PublishedFactor]
    coverage: list[PublishedSicCoverage]
