from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request

from gabi.application.portfolio.journal import Journal
from gabi_api.schemas.journal import (
    JournalChanges,
    JournalCreate,
    JournalEntry,
    JournalList,
    JournalReview,
    ThesisCounts,
)

router = APIRouter(prefix="/api/v1/portfolio/journal", tags=["portfolio"])


def service(request: Request) -> Journal:
    return request.app.state.journal


@router.get("", response_model=JournalList)
def list_entries(journal: Annotated[Journal, Depends(service)],
                 limit: Annotated[int, Query(ge=1, le=100)] = 50,
                 offset: Annotated[int, Query(ge=0, le=100000)] = 0,
                 only_open: bool = False,
                 symbol: Annotated[str | None, Query(min_length=1, max_length=20)] = None) -> JournalList:
    items, total = journal.list(limit, offset, only_open, symbol)
    return JournalList(items=[JournalEntry.model_validate(item) for item in items],
                       total=total, limit=limit, offset=offset)


@router.get("/symbols", response_model=ThesisCounts)
def thesis_counts(journal: Annotated[Journal, Depends(service)]) -> ThesisCounts:
    """Open and total theses per company, for marking positions without a thesis."""
    return ThesisCounts.model_validate({"items": journal.thesis_counts()})


@router.get("/{entry_id}/changes", response_model=JournalChanges)
def changes(entry_id: Annotated[int, Path(ge=1)], journal: Annotated[Journal, Depends(service)]) -> JournalChanges:
    """Price, score and checklist now against the thesis; read from the cache, nothing is downloaded."""
    return JournalChanges.model_validate(journal.changes(entry_id))


@router.post("", response_model=JournalEntry, status_code=201)
def create(body: JournalCreate, journal: Annotated[Journal, Depends(service)]) -> JournalEntry:
    entry = journal.create(body.model_dump() | {"created_at": journal.today().isoformat()})
    return JournalEntry.model_validate(entry)


@router.post("/{entry_id}/review", response_model=JournalEntry)
def review(entry_id: Annotated[int, Path(ge=1)], body: JournalReview,
           journal: Annotated[Journal, Depends(service)]) -> JournalEntry:
    return JournalEntry.model_validate(journal.review(entry_id, journal.today(), body.review_price,
                                                      body.review_notes))


@router.post("/{entry_id}/delete", status_code=204)
def delete(entry_id: Annotated[int, Path(ge=1)], journal: Annotated[Journal, Depends(service)]) -> None:
    journal.delete(entry_id)
