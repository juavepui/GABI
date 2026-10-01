from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Path, Query, Request
from fastapi.responses import Response

from gabi.application.errors import QueryError
from gabi.application.market.evidence import EvidenceQueries
from gabi.application.market.queries import MarketQueries
from gabi.domain.market.selection import RankingFilter, RankingSort, SortKey
from gabi_api.schemas.evidence import CompanyEvidence, EvidenceTop, RankingStability
from gabi_api.schemas.market import (
    CompanyResponse,
    ComparisonResponse,
    DataResponse,
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


@router.get("/evidence", response_model=EvidenceTop)
def evidence_top(query: Evidence, frozen: bool = False) -> dict:
    return query.top(frozen=frozen)


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


@router.get("/model", response_model=ModelResponse)
def model(market: Service) -> ModelResponse:
    return model_response(market.model())


@router.get("/data/status", response_model=DataResponse)
def data_status(market: Service) -> DataResponse:
    return data_response(market.ranking(RankingFilter(hide_no_data=False), limit=1).data)


@router.get("/ranking", response_model=RankingResponse)
def ranking(market: Service, search: Annotated[str, Query(max_length=100)] = "",
            sectors: Annotated[list[str] | None, Query(max_length=11)] = None,
            min_market_cap: Annotated[float, Query(ge=0, le=1e15, allow_inf_nan=False)] = 0,
            golden_cross_only: bool = False, hide_no_data: bool = True,
            offset: Annotated[int, Query(ge=0, le=1000)] = 0,
            limit: Annotated[int, Query(ge=1, le=500)] = 100,
            order_by: SortKey = "composite_score", direction: Literal["asc", "desc"] = "desc",
            mode: Literal["INVESTOR", "RESEARCH"] | None = None,
            value: Annotated[float | None, Query(ge=0, le=1, allow_inf_nan=False)] = None,
            quality: Annotated[float | None, Query(ge=0, le=1, allow_inf_nan=False)] = None,
            momentum: Annotated[float | None, Query(ge=0, le=1, allow_inf_nan=False)] = None,
            risk: Annotated[float | None, Query(ge=0, le=1, allow_inf_nan=False)] = None) -> RankingResponse:
    overrides = {"value": value, "quality": quality, "momentum": momentum, "risk": risk}
    weights = None
    if any(weight is not None for weight in overrides.values()):
        if any(weight is None for weight in overrides.values()):
            raise QueryError("invalid_weights", "Indica los cuatro pesos para experimentar.", 422)
        weights = {key: float(weight) for key, weight in overrides.items() if weight is not None}
    result = market.ranking(RankingFilter(search, tuple(sectors or ()), min_market_cap, golden_cross_only, hide_no_data),
                            offset, limit, weights, mode, RankingSort(order_by, direction))
    return ranking_response(result)


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
                                   generated_at=result.snapshot.generated_at, revision=result.snapshot.revision)


@router.get("/comparison", response_model=ComparisonResponse)
def comparison(market: Service, symbols: Annotated[list[str], Query(min_length=2, max_length=5)]) -> ComparisonResponse:
    result = market.compare(symbols)
    return ComparisonResponse(items=[company_row(str(symbol), row, result) for symbol, row in result.rows.iterrows()],
                              model=model_response(result.model), data=data_response(result.data),
                              generated_at=result.snapshot.generated_at, revision=result.snapshot.revision)
