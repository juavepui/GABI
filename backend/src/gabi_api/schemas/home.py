from pydantic import BaseModel

from gabi_api.schemas.market import DataResponse


class HomeTarget(BaseModel):
    symbol: str
    name: str | None
    sector: str | None
    composite_score: float
    weight_pct: float


class HomeLastUpdate(BaseModel):
    kind: str
    finished_at: str | None


class HomeSteps(BaseModel):
    fred_key: bool
    universe: bool
    data_loaded: bool | None
    updated: bool


class HomeResponse(BaseModel):
    """The home page. `ranking_ready=False`: the frozen ranking is not cached yet (ask again with compute)."""

    as_of: str
    model_id: str
    ranking_ready: bool
    data: DataResponse | None
    target: list[HomeTarget]
    target_positions: int
    last_update: HomeLastUpdate | None
    steps: HomeSteps
