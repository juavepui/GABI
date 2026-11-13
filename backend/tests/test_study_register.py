"""Dated classification of sealed studies (ADR 0008, phase 3)."""

import json
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
REGISTER = json.loads((ROOT / "docs/studies/register.json").read_text(encoding="utf-8"))
DECISIONS = {"continue", "replace", "finish_then_close", "closed"}
STUDIES = REGISTER["studies"]


def test_register_points_to_its_adr():
    assert (ROOT / REGISTER["adr"]).is_file()


@pytest.mark.parametrize("study", STUDIES, ids=lambda study: study["id"])
def test_each_study_has_a_dated_decision_and_existing_references(study):
    assert study["decision"] in DECISIONS and study["reason"].strip()
    assert date.fromisoformat(study["decided"]) and study["issues"]
    for path in study["pinned_paths"] + study["docs"]:
        assert (ROOT / path).is_file(), path
    if study["kind"] == "prospective":
        first = date.fromisoformat(study["first_record"])
        assert all(date.fromisoformat(review) > first for review in study["reviews"])
    if study["decision"] == "closed":
        assert date.fromisoformat(study["closed"]) >= date.fromisoformat(study["decided"])
        assert "last_record" in study and study["evidence_state"]


def test_study_ids_are_unique_and_objectives_are_not_studies():
    ids = [study["id"] for study in STUDIES]
    assert len(ids) == len(set(ids))
    assert all(objective["decision"] in DECISIONS for objective in REGISTER["objectives"])
    assert not {objective["id"] for objective in REGISTER["objectives"]} & set(ids)
