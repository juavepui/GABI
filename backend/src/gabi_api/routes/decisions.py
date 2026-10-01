from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Request
from fastapi.responses import Response

from gabi.application.portfolio.decisions import Decisions, decisions_frame
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
JobId = Annotated[str, Path(pattern=r"^[a-f0-9]{32}$")]
CSV: dict[int | str, dict[str, Any]] = {200: {"content": {"text/csv": {}}, "description": "Decisiones en CSV"}}


@router.get("", response_model=DecisionList)
def list_plans(decisions: Service) -> DecisionList:
    return DecisionList(items=[DecisionSummary.model_validate(row) for row in decisions.list()])


def _csv(rows: list[dict], name: str) -> Response:
    # As the old download: plan["decisions"].to_csv(index=False) in utf-8-sig, the BOM Excel needs.
    body = decisions_frame(rows).to_csv(index=False, lineterminator="\n").encode("utf-8-sig")
    return Response(body, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/jobs/{job_id}/decisions.csv", response_class=Response, responses=CSV)
def job_csv(job_id: JobId, decisions: Service) -> Response:
    """The freshly generated plan, before saving it (the old «Descargar decisiones CSV»)."""
    return _csv(decisions.job_plan(job_id)["decisions"], "gabi_decisiones.csv")


@router.get("/{plan_id}/decisions.csv", response_class=Response, responses=CSV)
def plan_csv(plan_id: PlanId, decisions: Service) -> Response:
    return _csv(decisions.get(plan_id)["decisions"], f"gabi_decisiones_{plan_id}.csv")


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
