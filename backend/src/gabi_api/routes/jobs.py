import hashlib
import json
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi import Path as ApiPath
from pydantic import BaseModel, Field

from gabi.application.administration.jobs import JobCommand, Jobs
from gabi.application.administration.model import ModelCommands
from gabi.application.errors import QueryError
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
    command = JobCommand(body.kind, tuple(body.symbols), body.start, body.end)
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
def job_result(job_id: JobId, service: Service, local: Local) -> dict:
    job = service.get(job_id)
    if job["status"] != "succeeded" or job["result_ref"] != job_id or not job["result_sha256"]:
        raise QueryError("result_unavailable", "El resultado aún no está disponible.", 404)
    if job["kind"] in {"maintenance", "tiingo"}:
        raise QueryError("result_restricted", "Este resultado pertenece al seguimiento ciego.", 403)
    artifact = Path(local.data_dir) / "jobs" / "results" / f"{job_id}.json"
    try:
        raw = artifact.read_bytes()
        if len(raw) > 10_000_000 or hashlib.sha256(raw).hexdigest() != job["result_sha256"]:
            raise ValueError("Result hash mismatch")
        return json.loads(raw)
    except (OSError, ValueError) as exc:
        raise QueryError("result_unavailable", "El artefacto no se puede verificar.", 503) from exc
