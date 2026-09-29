"""The only HTTP composition root. Importing it never opens application data."""
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import date
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException

from gabi.application.administration.model import ModelQueries
from gabi.application.errors import QueryError
from gabi.application.market.queries import MarketQueries
from gabi.infrastructure.legacy.market import calculators, defaults, model_policy
from gabi.infrastructure.settings import Settings
from gabi.infrastructure.storage.market import ReadOnlyMarket
from gabi_api.routes.market import router


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
    status: str = "error"


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "GABI"
    api_version: str = "v1"


def create_app(settings: Settings | None = None, *, today: Callable[[], date] = date.today) -> FastAPI:
    settings = settings or Settings.from_environment()
    benchmark, risk_free_rate = defaults()
    policy = model_policy()
    repository = ReadOnlyMarket(settings, calculators(), policy, benchmark, risk_free_rate)
    market = MarketQueries(repository, ModelQueries(repository, policy), today)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            yield
        finally:
            market.close()

    errors: dict[int | str, dict[str, Any]] = {status: {"model": ErrorResponse} for status in (403, 404, 409, 422, 500, 503)}
    app = FastAPI(title="GABI local API", version="1.0.0", lifespan=lifespan, responses=errors)
    app.state.market = market
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_methods=["GET"],
                       allow_headers=["Accept", "Content-Type"], allow_credentials=False)

    def error(code: str, message: str, status: int) -> JSONResponse:
        return JSONResponse(status_code=status, content=ErrorResponse(error=ErrorDetail(code=code, message=message)).model_dump())

    @app.exception_handler(QueryError)
    async def query_error(request: Request, exc: QueryError) -> JSONResponse:
        return error(exc.code, exc.message, exc.status)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
        return error("invalid_request", "Los parámetros de consulta no son válidos.", 422)

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        return error("internal_error", "No se puede completar la consulta local.", 500)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return error("http_error", "La ruta o el método solicitado no está disponible.", exc.status_code)

    @app.get("/api/v1/health", response_model=HealthResponse, tags=["administration"])
    def health() -> HealthResponse:
        return HealthResponse()

    app.include_router(router)
    return app


def main() -> None:
    import uvicorn

    # No host option/environment override: the supported launcher only listens locally.
    uvicorn.run(create_app(), host="127.0.0.1", port=8000, access_log=False)


if __name__ == "__main__":
    main()
