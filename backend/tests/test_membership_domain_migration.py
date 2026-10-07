"""Original index-event replay, errors and immutable explicit inputs."""

import copy
import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from gabi.domain.research.membership import apply_reviewed_extension, extend_membership

REFERENCE = json.loads((Path(__file__).parent / "fixtures/membership_migration.json").read_text(encoding="utf-8"))
TODAY = date.fromisoformat(REFERENCE["today"])


@pytest.mark.parametrize("case", REFERENCE["cases"], ids=lambda case: case["name"])
def test_replay_and_errors_match_original(case):
    frame, ledger = pd.DataFrame(case["history"]), copy.deepcopy(case["ledger"])
    before = frame.copy(deep=True)
    if "error" in case:
        with pytest.raises(ValueError) as caught:
            extend_membership(frame, ledger, today=TODAY)
        assert str(caught.value) == case["error"]
    else:
        result = extend_membership(frame, ledger, today=TODAY)
        pd.testing.assert_frame_equal(result, pd.DataFrame(case["expected"]))
        pd.testing.assert_frame_equal(result, extend_membership(result, ledger, today=TODAY))
    pd.testing.assert_frame_equal(frame, before)
    assert ledger == case["ledger"]


def test_explicit_day_without_files_and_custom_history_is_unchanged(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("file access")

    monkeypatch.setattr(Path, "open", forbidden)
    case = REFERENCE["cases"][0]
    frame = pd.DataFrame(case["history"])
    assert len(extend_membership(frame, case["ledger"], today=TODAY)) == 3
    custom = pd.DataFrame([{"date": "2023-12-31", "tickers": "X,Y"}])
    assert apply_reviewed_extension(custom, case["ledger"], today=TODAY) is custom
    with pytest.raises(TypeError):
        extend_membership(frame, case["ledger"])
    with pytest.raises(ValueError, match="verification interval"):
        extend_membership(frame, case["ledger"], today=date(2024, 3, 30))
