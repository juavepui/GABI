from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request

from gabi.application.portfolio.decisions import Decisions
from gabi_api.schemas.decisions import (
    DecisionJobSave,
    DecisionList,
    DecisionProgress,
    DecisionRename,
    DecisionSummary,
    DeleteDecision,
    SavedDecision,
)

router = APIRouter(prefix="/api/v1/portfolio/decisions", tags=["portfolio"])


def service(request: Request) -> Decisions:
    return request.app.state.decisions


Service = Annotated[Decisions, Depends(service)]
PlanId = Annotated[int, Path(ge=1)]


@router.get("", response_model=DecisionList)
def list_plans(decisions: Service) -> DecisionList:
    return DecisionList(items=[DecisionSummary.model_validate(row) for row in decisions.list()])


@router.get("/{plan_id}", response_model=SavedDecision)
def plan(plan_id: PlanId, decisions: Service) -> SavedDecision:
    return SavedDecision.model_validate(decisions.get(plan_id))


@router.get("/{plan_id}/progress", response_model=DecisionProgress)
def progress(plan_id: PlanId, decisions: Service) -> DecisionProgress:
    return DecisionProgress.model_validate(decisions.progress(plan_id))


@router.post("", response_model=SavedDecision, status_code=201)
def save(body: DecisionJobSave, decisions: Service) -> SavedDecision:
    return SavedDecision.model_validate(decisions.save_job(body.job_id, body.name))


@router.post("/{plan_id}/rename", response_model=SavedDecision)
def rename(plan_id: PlanId, body: DecisionRename, decisions: Service) -> SavedDecision:
    return SavedDecision.model_validate(decisions.rename(plan_id, body.name))


@router.post("/{plan_id}/delete", response_model=DeleteDecision)
def delete(plan_id: PlanId, decisions: Service) -> DeleteDecision:
    return DeleteDecision(deleted=decisions.delete(plan_id))
