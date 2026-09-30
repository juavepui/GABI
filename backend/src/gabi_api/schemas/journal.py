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


class JournalList(WireModel):
    items: list[JournalEntry]
    total: int
    limit: int
    offset: int
