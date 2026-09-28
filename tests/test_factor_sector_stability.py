"""Historical labels, provenance, missingness and descriptive-only contracts of #48."""

import hashlib
import json
import zipfile

import numpy as np
import pandas as pd
import pytest

from gabi import factor_sector_stability as sector


@pytest.fixture
def spec():
    return sector.specification()


def filings(*overrides):
    return pd.DataFrame([{**{"accn": str(i), "cik": "0000000001", "sic": "3571", "form": "10-Q",
                              "filed_date": "2020-01-10", "accepted": "2020-01-10 17:00:00.0",
                              "source_url": "https://www.sec.gov/2020q1.zip"}, **values}
                         for i, values in enumerate(overrides)])


def assigned(spec, records, date="2020-03-01"):
    frame = pd.DataFrame({"entity_id": ["cik:0000000001"]}, index=["RENAMED"])
    return sector.assign(frame, date, records, spec).iloc[0]


def test_published_spec_is_fixed_and_descriptive(spec):
    assert sector.fingerprint(spec) == sector.SPEC_SHA256
    assert spec["stage"] == "RESEARCH_RETROSPECTIVE_DESCRIPTIVE"
    assert len(spec["signals"]) == 13 and len(spec["divisions"]) == 10
    assert spec["minimum_pairs"] == 30 and spec["minimum_summary_periods"] == 30


def test_historical_cik_and_same_day_or_future_labels(spec):
    history = filings({}, {"accn": "later", "sic": "6021", "filed_date": "2020-03-01", "accepted": "2020-03-01 08:00:00"},
                      {"accn": "future_accept", "sic": "6021", "filed_date": "2020-02-29", "accepted": "2020-03-01 08:00:00"},
                      {"accn": "other_cik", "cik": "0000000002", "sic": "6021"})
    result = assigned(spec, history)
    assert result.accn == "0" and result.division == "D"
    assert result.cik == "0000000001"
    missing = pd.DataFrame({"entity_id": ["ticker:RENAMED"]}, index=["RENAMED"])
    assert sector.assign(missing, "2020-03-01", history, spec).iloc[0].reason == "missing_identity"


@pytest.mark.parametrize("sic", ["", "9900", "6021.0", "0000", "unknown"])
def test_invalid_latest_label_does_not_fall_back(spec, sic):
    result = assigned(spec, filings({}, {"sic": sic, "filed_date": "2020-02-10", "accepted": "2020-02-10 17:00:00"}))
    assert result.reason == "invalid_or_unclassified_sic" and result.division == ""


def test_ambiguity_missing_dates_and_stale_filings(spec):
    assert assigned(spec, filings({}, {"sic": "6021"})).reason == "ambiguous_latest_sic"
    assert assigned(spec, filings({}, {"sic": "6021", "filed_date": "2020-02-10", "accepted": ""})).reason == "unknown_acceptance_date"
    assert assigned(spec, filings({"filed_date": ""})).reason == "unknown_filing_date"
    assert assigned(spec, filings({}), "2021-02-15").reason == "stale_filing"
    # EDGAR legitimately assigns next-business-day filed_date to after-hours submissions.
    assert assigned(spec, filings({"filed_date": "2020-02-11", "accepted": "2020-02-10 18:00:00"})).reason == "classified"


@pytest.mark.parametrize("value, expected", [("0100", "A"), ("999", "A"), ("1000", "B"), ("1799", "C"),
                                            ("2000", "D"), ("4900", "E"), ("5199", "F"), ("5999", "G"),
                                            ("6799", "H"), ("8999", "I"), ("9799", "J"), ("9900", None)])
def test_fixed_sic_divisions(spec, value, expected):
    assert sector.sic_division(value, spec["divisions"]) == expected


def test_pairs_threshold_constants_and_missing_outcomes(spec):
    frame = pd.DataFrame({"pe_pct": np.arange(32, dtype=float), "retorno": np.arange(32, dtype=float),
                          "division": ["D"] * 32, "cik": ["0000000001"] * 32, "accn": ["x"] * 32,
                          "reason": ["classified"] * 32})
    frame.loc[31, "retorno"] = np.nan
    frame.loc[30, "division"] = ""
    rows = sector.quarter_rows(frame, "2020-03-01", "pe", spec)
    assert len(rows) == 10  # Includes every unpopulated group, not only estimable groups.
    d = next(r for r in rows if r["division"] == "D")
    assert d["n_eligible"] == 31 and d["n_pairs"] == 30 and d["ic"] == pytest.approx(1)
    coverage = sector.coverage_rows(frame, "2020-03-01")
    assert coverage[0]["n_eligible"] == 32 and coverage[0]["n_classified"] == 31
    assert coverage[2]["n_eligible"] == 1 and coverage[2]["n_classified"] == 1
    small_spec = {**spec, "signals": ["pe"]}
    signals = sector.factor_coverage_rows(frame, "2020-03-01", small_spec)[0]
    assert signals["n_pairs"] == 31 and signals["n_unknown_division_pairs"] == 1
    frame.loc[29, "retorno"] = np.inf
    d = next(r for r in sector.quarter_rows(frame, "2020-03-01", "pe", spec) if r["division"] == "D")
    assert d["n_pairs"] == 29 and d["ic"] is None and d["status"] == "insufficient_pairs"
    frame["retorno"] = 1.0
    d = next(r for r in sector.quarter_rows(frame, "2020-03-01", "pe", spec) if r["division"] == "D")
    assert d["status"] == "constant_series" and d["ic"] is None


def test_equal_quarter_summary_keeps_all_groups_and_fixed_windows(spec):
    panel = pd.DataFrame([{"fecha": "2015-10-02", "metric": "pe", "division": "D", "ic": .1, "n_pairs": 100},
                          {"fecha": "2016-01-02", "metric": "pe", "division": "D", "ic": .3, "n_pairs": 30},
                          {"fecha": "2021-01-02", "metric": "pe", "division": "D", "ic": None, "n_pairs": 29}])
    result = sector.summary(panel, spec)
    d = result["pe"]["D"]
    assert d["ic_mean"] == pytest.approx(.2)  # Quarter weight, not pair-count weight.
    assert d["n_periods"] == 2 and d["status"] == "insufficient_periods"
    assert d["windows"]["2011-15"]["ic_mean"] == .1
    assert d["windows"]["2016-20"]["ic_mean"] == .3
    assert d["windows"]["2021-25"]["ic_mean"] is None
    assert result["pe"]["A"]["n_periods"] == 0 and result["pe"]["A"]["ic_mean"] is None
    assert "p" not in d and "classification" not in d


def test_archive_primary_registrant_and_metadata_integrity(tmp_path):
    path = tmp_path / "2020q1.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("sub.txt", "adsh\tcik\tsic\tform\tfiled\taccepted\taciks\n0\t1\t3571\t10-Q\t20200110\t2020-01-10 17:00:00.0\t2\n")
    expected = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size, "fetched_at": "2026-09-28"}
    assert sector.verify_archive(path, expected, filings({}))["verified_filings"] == 1
    for changed in ({"sic": "6021"}, {"cik": "0000000002"}):
        with pytest.raises(ValueError, match="Metadatos"):
            sector.verify_archive(path, expected, filings(changed))
    path.write_bytes(path.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="Archivo SEC modificado"):
        sector.verify_archive(path, expected, filings({}))


def test_frozen_inputs_checked_before_outcomes(tmp_path, monkeypatch):
    output = tmp_path / "docs" / "factor-zoo"
    output.mkdir(parents=True)
    original = {"inputs_sha256": {"changed.csv": "0" * 64}}
    (output / "resultado.json").write_text(json.dumps(original), encoding="utf-8")
    (tmp_path / "changed.csv").write_text("not an outcome CSV", encoding="utf-8")
    monkeypatch.setattr(sector.config, "BASE_DIR", tmp_path)
    monkeypatch.setattr(sector, "ORIGINAL_SHA256", sector.fingerprint(original))
    with pytest.raises(ValueError, match="Input congelado modificado"):
        sector.frozen_frames()


def test_existing_supplement_cannot_be_overwritten(tmp_path, monkeypatch):
    monkeypatch.setattr(sector, "OUTPUT", tmp_path)
    (tmp_path / "resultado.json").write_text("frozen", encoding="utf-8")
    with pytest.raises(ValueError, match="ya está congelado"):
        sector.analyze()
    assert (tmp_path / "resultado.json").read_text() == "frozen"


def test_saved_view_detects_artifact_tampering(tmp_path, monkeypatch, spec):
    from pathlib import Path

    monkeypatch.setattr(sector, "OUTPUT", tmp_path)
    (tmp_path / "preregistro.json").write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    data = tmp_path / "coverage.csv"
    data.write_text("fecha,n_eligible\n2020-01-01,100\n", encoding="utf-8")
    result = {"spec_sha256": sector.SPEC_SHA256,
              "code_sha256": sector.file_hash(Path(sector.__file__), text=True),
              "artifacts_sha256": {"coverage.csv": sector.file_hash(data, text=True)}}
    (tmp_path / "resultado.json").write_text(json.dumps(result), encoding="utf-8")
    expected = sector.fingerprint(result)
    assert sector.load_saved(expected) == result
    data.write_text("fecha,n_eligible\n2020-01-01,101\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Artefacto SIC modificado"):
        sector.load_saved(expected)
