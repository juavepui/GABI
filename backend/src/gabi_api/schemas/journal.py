from datetime import date

from pydantic import Field

from gabi_api.schemas.market import WireModel


class JournalCreate(WireModel):
    symbol: str = Field(min_length=1, max_length=20)
    horizon: str | None = Field(default=None, max_length=100)
    entry_price: float | None = Field(default=None, allow_inf_nan=False)
    thesis: str | None = Field(default="", max_length=5000)
    bear_price: float | None = Field(default=None, allow_inf_nan=False)
    base_price: float | None = Field(default=None, allow_inf_nan=False)
    bull_price: float | None = Field(default=None, allow_inf_nan=False)
    bear_prob: float | None = Field(default=None, allow_inf_nan=False)
    base_prob: float | None = Field(default=None, allow_inf_nan=False)
    bull_prob: float | None = Field(default=None, allow_inf_nan=False)
    catalysts: str | None = Field(default="", max_length=5000)
    risks: str | None = Field(default="", max_length=5000)
    position_size_pct: float | None = Field(default=None, allow_inf_nan=False)
    notes: str | None = Field(default="", max_length=5000)
    invalidation: str | None = Field(default="", max_length=5000, description="Qué invalidaría la tesis")
    review_due: date | None = Field(default=None, description="Fecha en que revisarla; vacía = fin del horizonte")


class JournalReview(WireModel):
    review_price: float | None = Field(default=None, allow_inf_nan=False)
    review_notes: str = Field(default="", max_length=5000)


class ExpectedValue(WireModel):
    expected_price: float
    expected_return_pct: float
    probs_summed_to_100: bool


class JournalEntry(JournalCreate):
    id: int
    created_at: date
    status: str
    review_date: date | None
    review_price: float | None
    review_notes: str | None
    expected_value: ExpectedValue | None
    # Captured when the thesis was written (#186); absent on entries written before.
    entry_price_date: date | None = None
    entry_score: float | None = Field(default=None, description="Score del modelo congelado al escribirla · 0 a 100")
    model_id: str | None = None
    entry_checklist_passed: int | None = None
    entry_checklist_evaluated: int | None = None


class JournalList(WireModel):
    items: list[JournalEntry]
    total: int
    limit: int
    offset: int


class ThesisCount(WireModel):
    open: int
    total: int


class ThesisCounts(WireModel):
    items: dict[str, ThesisCount]


class JournalChanges(WireModel):
    """What moved since the thesis: now against what was captured when it was written."""

    entry_id: int
    symbol: str
    as_of: date
    price: float | None
    price_date: date | None
    entry_price: float | None
    price_return: float | None = Field(description="Fracción: 0,1 = +10 % desde el precio de entrada")
    score: float | None
    entry_score: float | None
    same_model: bool
    score_change: float | None
    checklist_passed: int | None
    checklist_evaluated: int | None
    entry_checklist_passed: int | None
    entry_checklist_evaluated: int | None
    checklist_change: int | None
