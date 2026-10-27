from fastapi import APIRouter

from gabi_api.schemas.forms import FormDefaults

router = APIRouter(prefix="/api/v1/forms", tags=["administration"])


@router.get("/defaults", response_model=FormDefaults)
def defaults() -> FormDefaults:
    """Starting values of the decision, simulation, backtest and Portfolio Lab forms; constant, no data read."""
    return FormDefaults()
