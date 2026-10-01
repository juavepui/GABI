from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request

from gabi.application.portfolio.journal import Journal
from gabi_api.schemas.journal import JournalCreate, JournalEntry, JournalList, JournalReview

router = APIRouter(prefix="/api/v1/portfolio/journal", tags=["portfolio"])


def service(request: Request) -> Journal:
    return request.app.state.journal


@router.get("", response_model=JournalList)
def list_entries(journal: Annotated[Journal, Depends(service)],
                 limit: Annotated[int, Query(ge=1, le=100)] = 50,
                 offset: Annotated[int, Query(ge=0, le=100000)] = 0,
                 only_open: bool = False) -> JournalList:
    items, total = journal.list(limit, offset, only_open)
    return JournalList(items=[JournalEntry.model_validate(item) for item in items],
                       total=total, limit=limit, offset=offset)


@router.post("", response_model=JournalEntry, status_code=201)
def create(body: JournalCreate, journal: Annotated[Journal, Depends(service)]) -> JournalEntry:
    entry = journal.create(body.model_dump() | {"created_at": date.today().isoformat()})
    return JournalEntry.model_validate(entry)


@router.post("/{entry_id}/review", response_model=JournalEntry)
def review(entry_id: Annotated[int, Path(ge=1)], body: JournalReview,
           journal: Annotated[Journal, Depends(service)]) -> JournalEntry:
    return JournalEntry.model_validate(journal.review(entry_id, date.today(), body.review_price, body.review_notes))


@router.post("/{entry_id}/delete", status_code=204)
def delete(entry_id: Annotated[int, Path(ge=1)], journal: Annotated[Journal, Depends(service)]) -> None:
    journal.delete(entry_id)
