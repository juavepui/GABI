"""Reference labels, interval replacement and validation of reviewed nominations."""

import copy
import json
from pathlib import Path

import pytest

from gabi.domain.research.ticker_corrections import apply_nominations, correct_symbols, parse_nominations

REFERENCE = json.loads((Path(__file__).parent / "fixtures/ticker_corrections_migration.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", REFERENCE["symbols"])
def test_label_reference(case):
    symbols = set(case["symbols"])
    if "error" in case:
        with pytest.raises(ValueError) as caught:
            correct_symbols(symbols, case["day"])
        assert str(caught.value) == case["error"]
    else:
        result, changes = correct_symbols(symbols, case["day"])
        assert sorted(result) == case["expected"] and changes == case["changes"]
    assert symbols == set(case["symbols"])


@pytest.mark.parametrize("case", REFERENCE["applications"], ids=lambda case: case["name"])
def test_nomination_application_reference(case):
    rows, entries = copy.deepcopy(case["community"]), copy.deepcopy(case["entries"])
    parsed = parse_nominations(entries)
    result = apply_nominations(rows, parsed)
    assert json.loads(json.dumps(result)) == case["expected"]
    assert entries == case["entries"] and rows == case["community"]
    assert parsed[0]["sec_tickers"] == tuple(entries[0]["sec_tickers"])


@pytest.mark.parametrize("change", ["interval", "cik", "tickers", "overlap"])
def test_nomination_validation_without_files(change, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("file access")

    monkeypatch.setattr(Path, "open", forbidden)
    entry = copy.deepcopy(REFERENCE["applications"][0]["entries"][0])
    rows = [entry]
    if change == "interval":
        entry["valid_to"] = entry["valid_from"]
    elif change == "cik":
        entry["cik"] = "bad"
    elif change == "tickers":
        entry["sec_tickers"] = []
    else:
        rows.append(dict(entry, valid_from="2021-01-01"))
    with pytest.raises(ValueError, match="nomination"):
        parse_nominations(rows)


def test_correction_provenance_does_not_share_mutable_inputs():
    sources = ["https://source.example/reviewed"]
    _, changes = correct_symbols({"ANTM"}, "2012-01-01", source_urls=sources)
    changes[0]["source_urls"].append("other")
    assert sources == ["https://source.example/reviewed"]


def test_adjacent_nomination_intervals_are_not_overlapping():
    entry = copy.deepcopy(REFERENCE["applications"][0]["entries"][0])
    entries = [entry, dict(entry, valid_from=entry["valid_to"], valid_to="2030-01-01")]
    assert len(parse_nominations(entries)) == 2


def test_future_revalidation_provenance_includes_actual_domain_sources():
    from gabi.historical_revalidation import extra_sources

    root = Path(__file__).resolve().parents[1] / "src/gabi"
    sources = set(extra_sources())
    assert {root / name for name in ("domain/market/sec_facts.py", "domain/research/periods.py",
                                    "domain/research/ticker_corrections.py", "domain/research/membership.py")} <= sources
