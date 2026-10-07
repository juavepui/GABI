"""Reference Form 4 interpretation and summaries captured before extraction."""

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from gabi.domain.market.insiders import parse_form4_xml, summarize_insider_activity
from gabi.infrastructure.legacy.company import LegacyCompanyMath

REFERENCE = json.loads((Path(__file__).parent / "fixtures/insider_migration.json").read_text(encoding="utf-8"))
COLUMNS = ("transaction_date", "transaction_code", "owner_name", "shares", "price_per_share", "is_10b5_1_plan")


@pytest.mark.parametrize("case", REFERENCE["xml"])
def test_form4_reference(case):
    assert parse_form4_xml(case["text"]) == case["expected"]


@pytest.mark.parametrize("case", REFERENCE["summaries"])
def test_summary_reference(case):
    frame = pd.DataFrame(case["rows"], columns=COLUMNS)
    before = frame.copy(deep=True)
    result = summarize_insider_activity(frame, case["months"], as_of=date.fromisoformat(REFERENCE["as_of"]))
    recent = result.pop("recent")
    expected = dict(case["expected"])
    expected_recent = pd.DataFrame(expected.pop("recent"), columns=COLUMNS)
    assert result == expected
    pd.testing.assert_frame_equal(recent.reset_index(drop=True), expected_recent, check_dtype=False)
    pd.testing.assert_frame_equal(frame, before)


def test_explicit_day_without_io_or_implicit_clock(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("implicit clock or IO")

    monkeypatch.setattr(Path, "open", forbidden)
    monkeypatch.setattr(pd.Timestamp, "now", forbidden)
    frame = pd.DataFrame(REFERENCE["summaries"][0]["rows"], columns=COLUMNS)
    day = date.fromisoformat(REFERENCE["as_of"])
    result = LegacyCompanyMath.insiders("ACME", frame, 6, day)
    assert result["n_buys"] == 3
    assert result["n_sells"] == 1
    assert result["net_value"] == 850.0
    # The historical implementation includes future rows; migration preserves this.
    assert result["recent"].iloc[-1]["transaction_date"] == "2024-09-01"
    with pytest.raises(TypeError):
        summarize_insider_activity(frame)
