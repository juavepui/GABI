from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request

from gabi.application.portfolio.simulations import Simulations
from gabi_api.schemas.simulations import (
    SimulationCreate,
    SimulationList,
    SimulationPortfolio,
    SimulationResult,
    SimulationTrade,
    SimulationTradeCreate,
    SimulationTrades,
    UndoResult,
)

router = APIRouter(prefix="/api/v1/portfolio/simulations", tags=["portfolio"])


def service(request: Request) -> Simulations:
    return request.app.state.simulations


@router.get("", response_model=SimulationList)
def portfolios(simulations: Annotated[Simulations, Depends(service)]) -> SimulationList:
    return SimulationList(items=[SimulationPortfolio.model_validate(row) for row in simulations.portfolios()])


@router.post("", response_model=SimulationPortfolio, status_code=201)
def create(body: SimulationCreate, simulations: Annotated[Simulations, Depends(service)]) -> SimulationPortfolio:
    return SimulationPortfolio.model_validate(simulations.create(body.model_dump()))


@router.get("/{portfolio_id}", response_model=SimulationPortfolio)
def portfolio(portfolio_id: Annotated[int, Path(ge=1)],
              simulations: Annotated[Simulations, Depends(service)]) -> SimulationPortfolio:
    return SimulationPortfolio.model_validate(simulations.portfolio(portfolio_id))


@router.get("/{portfolio_id}/trades", response_model=SimulationTrades)
def trades(portfolio_id: Annotated[int, Path(ge=1)],
           simulations: Annotated[Simulations, Depends(service)]) -> SimulationTrades:
    return SimulationTrades(items=[SimulationTrade.model_validate(row) for row in simulations.trades(portfolio_id)])


@router.post("/{portfolio_id}/trades", response_model=SimulationTrade, status_code=201)
def trade(portfolio_id: Annotated[int, Path(ge=1)], body: SimulationTradeCreate,
          simulations: Annotated[Simulations, Depends(service)]) -> SimulationTrade:
    return SimulationTrade.model_validate(simulations.trade(portfolio_id, body.model_dump()))


@router.post("/{portfolio_id}/undo", response_model=UndoResult)
def undo(portfolio_id: Annotated[int, Path(ge=1)],
         simulations: Annotated[Simulations, Depends(service)]) -> UndoResult:
    return UndoResult(undone=simulations.undo(portfolio_id))


@router.get("/{portfolio_id}/result", response_model=SimulationResult)
def result(portfolio_id: Annotated[int, Path(ge=1)],
           simulations: Annotated[Simulations, Depends(service)]) -> SimulationResult:
    return SimulationResult.model_validate(simulations.result(portfolio_id))
