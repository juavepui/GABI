from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Request
from fastapi import Path as ApiPath
from pydantic import BaseModel, Field

from gabi.application.administration.jobs import JobCommand, Jobs
from gabi.application.administration.model import ModelCommands
from gabi_api.schemas.jobs import CreateJobRequest, JobListResponse, JobResponse, LocalSettingsResponse
from gabi_api.schemas.market import ModelResponse, model_response

router = APIRouter(prefix="/api/v1", tags=["administration"])


def jobs(request: Request) -> Jobs:
    return request.app.state.jobs


def settings(request: Request) -> Any:
    return request.app.state.settings


def model_commands(request: Request) -> ModelCommands:
    return request.app.state.model_commands


Service = Annotated[Jobs, Depends(jobs)]
Local = Annotated[Any, Depends(settings)]
ModelCommand = Annotated[ModelCommands, Depends(model_commands)]
JobId = Annotated[str, ApiPath(pattern=r"^[a-f0-9]{32}$")]


class WeightsRequest(BaseModel):
    value: float = Field(ge=0, le=1, allow_inf_nan=False)
    quality: float = Field(ge=0, le=1, allow_inf_nan=False)
    momentum: float = Field(ge=0, le=1, allow_inf_nan=False)
    risk: float = Field(ge=0, le=1, allow_inf_nan=False)


class ModeRequest(BaseModel):
    mode: Literal["INVESTOR", "RESEARCH"]


@router.post("/administration/mode", response_model=ModelResponse)
def set_mode(body: ModeRequest, service: ModelCommand) -> ModelResponse:
    return model_response(service.set_mode(body.mode))


@router.post("/administration/weights", response_model=ModelResponse)
def save_weights(body: WeightsRequest, service: ModelCommand) -> ModelResponse:
    return model_response(service.save_weights(body.model_dump()))


@router.get("/administration/settings", response_model=LocalSettingsResponse)
def local_settings(local: Local) -> LocalSettingsResponse:
    import os

    keys = {name: bool(os.environ.get(env)) or (local.data_dir / filename).is_file()
            for name, env, filename in (("fred", "", "fred_api_key.txt"),
                                        ("tiingo", "TIINGO_API_KEY", "tiingo_api_key.txt"),
                                        ("fmp", "FMP_API_KEY", "fmp_api_key.txt"),
                                        ("nasdaq", "NASDAQ_DATA_LINK_API_KEY", "nasdaq_data_link_api_key.txt"))}
    return LocalSettingsResponse(keys=keys)


@router.post("/jobs", response_model=JobResponse, status_code=202)
def create_job(body: CreateJobRequest, service: Service) -> dict:
    command = JobCommand(body.kind, tuple(body.symbols), body.start, body.end, body.portfolio_id,
                         body.decision_policy.model_dump() if body.decision_policy else None, body.holdings_text,
                         body.snapshot_id, body.factor_months, body.factor_mode, body.factor_max_symbols,
                         body.backtest_options.model_dump(exclude_none=True) if body.backtest_options else None)
    return service.submit(command, body.idempotency_key)


@router.get("/jobs", response_model=JobListResponse)
def list_jobs(service: Service) -> JobListResponse:
    return JobListResponse(jobs=[JobResponse.model_validate(job) for job in service.list()])


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: JobId, service: Service) -> dict:
    return service.get(job_id)


@router.post("/jobs/{job_id}/cancel", response_model=JobResponse)
def cancel_job(job_id: JobId, service: Service) -> dict:
    return service.cancel(job_id)


@router.get("/jobs/{job_id}/result")
def job_result(job_id: JobId, service: Service) -> dict:
    return service.result(job_id)
