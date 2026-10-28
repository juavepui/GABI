from dataclasses import dataclass
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Path, Query, Request
from fastapi.responses import Response

from gabi.application.errors import QueryError
from gabi.application.market import comparison as compared
from gabi.application.market.analysis_prompt import AnalysisPrompt
from gabi.application.market.block_evidence import BlockEvidence
from gabi.application.market.checklist import CompanyChecklist
from gabi.application.market.company_research import CompanyResearch
from gabi.application.market.evidence import EvidenceQueries
from gabi.application.market.queries import MarketQueries
from gabi.domain.market.comparison import positions
from gabi.domain.market.selection import EarningsWindow, RankingFilter, RankingSort, SortKey
from gabi_api.ranking_export import ranking_csv
from gabi_api.schemas.checklist import (
    ChecklistPresetRequest,
    ChecklistSectorMultiples,
    ChecklistThresholds,
    ChecklistThresholdsRequest,
    CompanyChecklistResponse,
    ComparisonChecklistResponse,
)
from gabi_api.schemas.evidence import (
    CompanyEvidence,
    CompanyFilingChanges,
    CompanyInsiders,
    CompanyResearchResponse,
    EvidenceTop,
    RankingCoverage,
    RankingStability,
    ScoreBlocksEvidence,
)
from gabi_api.schemas.market import (
    METRIC_SOURCE_WIRE,
    AnalysisPromptResponse,
    CompanyResponse,
    ComparisonPricesResponse,
    ComparisonResponse,
    DataResponse,
    MetricGlossary,
    ModelResponse,
    PricePoint,
    RankingResponse,
    company_row,
    data_response,
    finite,
    model_response,
    ranking_response,
)

router = APIRouter(prefix="/api/v1", tags=["market"])


def service(request: Request) -> MarketQueries:
    return request.app.state.market


Service = Annotated[MarketQueries, Depends(service)]
SymbolPath = Annotated[str, Path(min_length=1, max_length=20, pattern=r"^[A-Za-z0-9^][A-Za-z0-9^.\-]*$")]


def evidence_service(request: Request) -> EvidenceQueries:
    return request.app.state.evidence


Evidence = Annotated[EvidenceQueries, Depends(evidence_service)]


def research_service(request: Request) -> CompanyResearch:
    return request.app.state.company_research


Research = Annotated[CompanyResearch, Depends(research_service)]


@router.get("/companies/{symbol}/research", response_model=CompanyResearchResponse)
def company_research(symbol: SymbolPath, query: Research) -> dict:
    return query.overview(symbol)


@router.get("/companies/{symbol}/insiders", response_model=CompanyInsiders)
def company_insiders(symbol: SymbolPath, query: Research) -> dict:
    return query.insiders(symbol)


@router.get("/companies/{symbol}/filing-changes", response_model=CompanyFilingChanges)
def company_filing_changes(symbol: SymbolPath, query: Research) -> dict:
    return query.filing_changes(symbol)


def checklist_service(request: Request) -> CompanyChecklist:
    return request.app.state.company_checklist


Checklist = Annotated[CompanyChecklist, Depends(checklist_service)]


@router.get("/companies/{symbol}/checklist", response_model=CompanyChecklistResponse)
def company_checklist(symbol: SymbolPath, query: Checklist) -> dict:
    return query.company(symbol)


@router.get("/companies/{symbol}/checklist/sector", response_model=ChecklistSectorMultiples)
def company_checklist_sector(symbol: SymbolPath, query: Checklist) -> dict:
    return query.sector_multiples(symbol)


@router.get("/checklist/thresholds", response_model=ChecklistThresholds)
def checklist_thresholds(query: Checklist) -> dict:
    return query.thresholds()


@router.post("/checklist/thresholds", response_model=ChecklistThresholds)
def save_checklist_thresholds(body: ChecklistThresholdsRequest, query: Checklist) -> dict:
    return query.save_thresholds(body.values)


@router.post("/checklist/thresholds/preset", response_model=ChecklistThresholds)
def apply_checklist_preset(body: ChecklistPresetRequest, query: Checklist) -> dict:
    return query.apply_preset(body.key)


@router.post("/checklist/thresholds/reset", response_model=ChecklistThresholds)
def reset_checklist_thresholds(query: Checklist) -> dict:
    return query.reset_thresholds()


@router.get("/score-blocks/evidence", response_model=ScoreBlocksEvidence)
def score_blocks_evidence(request: Request) -> dict:
    """Published Factor Zoo evidence of each score block; read-only, also in Investor mode."""
    query: BlockEvidence = request.app.state.block_evidence
    return query.summary()


@router.get("/evidence", response_model=EvidenceTop)
def evidence_top(query: Evidence, frozen: bool = False) -> dict:
    return query.top(frozen=frozen)


@router.get("/ranking/coverage", response_model=RankingCoverage)
def ranking_coverage(query: Evidence, threshold: Annotated[float, Query(ge=0, le=1)] = 0.7) -> dict:
    return query.coverage(threshold)


@router.get("/ranking/stability", response_model=RankingStability)
def ranking_stability(query: Evidence) -> dict:
    return query.stability()


@router.get("/companies/{symbol}/evidence", response_model=CompanyEvidence)
def company_evidence(symbol: SymbolPath, query: Evidence) -> dict:
    return query.company(symbol)


@router.get("/companies/{symbol}/evidence.json")
def company_evidence_download(symbol: SymbolPath, query: Evidence) -> Response:
    return Response(query.download(symbol), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="evidence-{symbol.upper()}.json"'})


@router.get("/companies/{symbol}/analysis-prompt", response_model=AnalysisPromptResponse)
def company_analysis_prompt(symbol: SymbolPath, request: Request) -> dict:
    prompts: AnalysisPrompt = request.app.state.analysis_prompt
    return prompts.prompt(symbol)


@router.get("/learn/metrics", response_model=MetricGlossary)
def metric_glossary(request: Request) -> dict:
    return request.app.state.metric_glossary


@router.get("/model", response_model=ModelResponse)
def model(market: Service) -> ModelResponse:
    return model_response(market.model())


@router.get("/data/status", response_model=DataResponse)
def data_status(market: Service) -> DataResponse:
    return data_response(market.ranking(RankingFilter(hide_no_data=False), limit=1).data)


@dataclass(frozen=True)
class Selection:
    filters: RankingFilter
    order: RankingSort
    weights: dict[str, float] | None
    mode: Literal["INVESTOR", "RESEARCH"] | None


def selection(search: Annotated[str, Query(max_length=100)] = "",
              sectors: Annotated[list[str] | None, Query(max_length=11)] = None,
              exclude_sectors: Annotated[list[str] | None, Query(max_length=11)] = None,
              min_market_cap: Annotated[float, Query(ge=0, le=1e15, allow_inf_nan=False)] = 0,
              golden_cross_only: bool = False, hide_no_data: bool = True,
              earnings: EarningsWindow | None = None, earnings_days: Annotated[int, Query(ge=0, le=90)] = 7,
              order_by: SortKey = "composite_score", direction: Literal["asc", "desc"] = "desc",
              mode: Literal["INVESTOR", "RESEARCH"] | None = None,
              value: Annotated[float | None, Query(ge=0, le=1, allow_inf_nan=False)] = None,
              quality: Annotated[float | None, Query(ge=0, le=1, allow_inf_nan=False)] = None,
              momentum: Annotated[float | None, Query(ge=0, le=1, allow_inf_nan=False)] = None,
              risk: Annotated[float | None, Query(ge=0, le=1, allow_inf_nan=False)] = None) -> Selection:
    overrides = {"value": value, "quality": quality, "momentum": momentum, "risk": risk}
    weights = None
    if any(weight is not None for weight in overrides.values()):
        if any(weight is None for weight in overrides.values()):
            raise QueryError("invalid_weights", "Indica los cuatro pesos para experimentar.", 422)
        weights = {key: float(weight) for key, weight in overrides.items() if weight is not None}
    filters = RankingFilter(search, tuple(sectors or ()), min_market_cap, golden_cross_only, hide_no_data,
                            tuple(exclude_sectors or ()), earnings, earnings_days)
    return Selection(filters, RankingSort(order_by, direction), weights, mode)


Selected = Annotated[Selection, Depends(selection)]


@router.get("/ranking", response_model=RankingResponse)
def ranking(market: Service, selected: Selected, offset: Annotated[int, Query(ge=0, le=1000)] = 0,
            limit: Annotated[int, Query(ge=1, le=500)] = 100) -> RankingResponse:
    result = market.ranking(selected.filters, offset, limit, selected.weights, selected.mode, selected.order)
    return ranking_response(result)


CSV: dict[int | str, dict[str, Any]] = {200: {"content": {"text/csv": {}}, "description": "Ranking en CSV"}}


@router.get("/ranking/export.csv", response_class=Response, responses=CSV)
def ranking_export(request: Request, market: Service, selected: Selected,
                   columns: Annotated[list[str] | None, Query(max_length=60)] = None) -> Response:
    """The filtered view with its visible columns, every row; the same calculation as /ranking."""
    result = market.ranking(selected.filters, 0, 1000, selected.weights, selected.mode, selected.order)
    query = "&".join(f"{key}={value}" for key, value in request.query_params.multi_items() if key != "columns")
    body = ranking_csv(result, columns or [], query).encode("utf-8-sig")  # the BOM Excel needs
    name = f"gabi_ranking_{result.snapshot.generated_at.date().isoformat()}.csv"
    return Response(body, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/companies/{symbol}", response_model=CompanyResponse)
def company(symbol: Annotated[str, Path(min_length=1, max_length=20, pattern=r"^[A-Za-z0-9^][A-Za-z0-9^.\-]*$")], market: Service,
            bars: Annotated[int, Query(ge=1, le=1000)] = 252) -> CompanyResponse:
    result, prices = market.company(symbol, bars)
    row = result.rows.iloc[0]
    return CompanyResponse(company=company_row(str(result.rows.index[0]), row, result),
                           model=model_response(result.model), data=data_response(result.data),
                           prices=[PricePoint.model_validate({"date": record["date"], "close": finite(record["close"]),
                                                              "adj_close": finite(record["adj_close"])})
                                   for record in prices.to_dict(orient="records")],
                                   metric_sources=METRIC_SOURCE_WIRE,
                                   generated_at=result.snapshot.generated_at, revision=result.snapshot.revision)


@router.get("/comparison", response_model=ComparisonResponse)
def comparison(request: Request, market: Service, symbols: Annotated[list[str], Query(min_length=2, max_length=5)]) -> ComparisonResponse:
    result = market.compare(symbols)
    items = [company_row(str(symbol), row, result) for symbol, row in result.rows.iterrows()]
    values = {item.symbol: {key: metric.value for key, metric in item.metrics.items()} for item in items}
    return ComparisonResponse(items=items, positions=positions(values, request.app.state.metric_directions),
                              metric_sources=METRIC_SOURCE_WIRE,
                              model=model_response(result.model), data=data_response(result.data),
                              generated_at=result.snapshot.generated_at, revision=result.snapshot.revision)


Compared = Annotated[list[str], Query(min_length=2, max_length=5)]


@router.get("/comparison/checklist", response_model=ComparisonChecklistResponse)
def comparison_checklist(market: Service, query: Checklist, symbols: Compared) -> dict:
    return compared.checklists(market, query, symbols)


@router.get("/comparison/prices", response_model=ComparisonPricesResponse)
def comparison_prices(market: Service, symbols: Compared, bars: Annotated[int, Query(ge=20, le=1000)] = 252) -> dict:
    return compared.prices(market, symbols, bars)
