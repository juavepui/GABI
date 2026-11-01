from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request

from gabi.application.portfolio.ideas import Ideas
from gabi_api.schemas.ideas import IdeaDetail, IdeaEventCreate, IdeaList, IdeaNoteText

router = APIRouter(prefix="/api/v1/portfolio/ideas", tags=["portfolio"])


def service(request: Request) -> Ideas:
    return request.app.state.ideas


Service = Annotated[Ideas, Depends(service)]
IdeaId = Annotated[int, Path(ge=1)]


@router.get("", response_model=IdeaList)
def list_ideas(ideas: Service, limit: Annotated[int, Query(ge=1, le=200)] = 200) -> IdeaList:
    """Every published idea, whatever its status, against the S&P 500 in EUR; reads only the local cache."""
    return IdeaList.model_validate(ideas.list(limit))


@router.get("/{idea_id}", response_model=IdeaDetail)
def get_idea(idea_id: IdeaId, ideas: Service) -> IdeaDetail:
    return IdeaDetail.model_validate(ideas.detail(idea_id))


@router.post("/{idea_id}/events", response_model=IdeaDetail, status_code=201)
def add_event(idea_id: IdeaId, body: IdeaEventCreate, ideas: Service) -> IdeaDetail:
    """Review, retire, close or correct: always a new event, never an edit."""
    return IdeaDetail.model_validate(ideas.append(idea_id, body.kind, body.model_dump()))


@router.post("/{idea_id}/notes", response_model=IdeaDetail, status_code=201)
def add_note(idea_id: IdeaId, body: IdeaNoteText, ideas: Service) -> IdeaDetail:
    return IdeaDetail.model_validate(ideas.add_note(idea_id, body.text))


@router.post("/{idea_id}/notes/{note_id}/save", response_model=IdeaDetail)
def save_note(idea_id: IdeaId, note_id: Annotated[int, Path(ge=1)], body: IdeaNoteText, ideas: Service) -> IdeaDetail:
    return IdeaDetail.model_validate(ideas.save_note(idea_id, note_id, body.text))


@router.post("/{idea_id}/notes/{note_id}/delete", response_model=IdeaDetail)
def delete_note(idea_id: IdeaId, note_id: Annotated[int, Path(ge=1)], ideas: Service) -> IdeaDetail:
    """Deletes a private note; the published events stay."""
    return IdeaDetail.model_validate(ideas.delete_note(idea_id, note_id))
