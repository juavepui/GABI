from typing import Annotated

from fastapi import APIRouter, Depends, Request

from gabi.application.market.watchlist import Watchlist
from gabi_api.routes.market import SymbolPath
from gabi_api.schemas.watchlist import (
    WatchlistChecklists,
    WatchlistCreate,
    WatchlistDeleted,
    WatchlistEntry,
    WatchlistNote,
    WatchlistSummary,
    WatchlistSymbols,
)

router = APIRouter(prefix="/api/v1/watchlist", tags=["market"])


def service(request: Request) -> Watchlist:
    return request.app.state.watchlist


Service = Annotated[Watchlist, Depends(service)]


@router.get("", response_model=WatchlistSummary)
def summary(watchlist: Service) -> WatchlistSummary:
    """Read-only from the frozen ranking and the journal: it never downloads nor initializes the table."""
    return WatchlistSummary.model_validate(watchlist.summary())


@router.get("/symbols", response_model=WatchlistSymbols)
def symbols(watchlist: Service) -> WatchlistSymbols:
    return WatchlistSymbols(symbols=watchlist.symbols())


@router.get("/checklist", response_model=WatchlistChecklists)
def checklists(watchlist: Service) -> WatchlistChecklists:
    """Criteria met / evaluable per followed company, computed from SQLite; separate because it is slower."""
    return WatchlistChecklists.model_validate(watchlist.checklists())


@router.post("", response_model=WatchlistEntry, status_code=201)
def add(body: WatchlistCreate, watchlist: Service) -> WatchlistEntry:
    return WatchlistEntry.model_validate(watchlist.add(body.symbol, body.note))


@router.post("/{symbol}", response_model=WatchlistEntry)
def update(symbol: SymbolPath, body: WatchlistNote, watchlist: Service) -> WatchlistEntry:
    return WatchlistEntry.model_validate(watchlist.update(symbol, body.note))


@router.post("/{symbol}/delete", response_model=WatchlistDeleted)
def delete(symbol: SymbolPath, watchlist: Service) -> WatchlistDeleted:
    return WatchlistDeleted(deleted=watchlist.delete(symbol))
