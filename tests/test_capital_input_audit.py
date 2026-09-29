"""Financial input integrity, missingness and read-only research isolation."""

import json
import sqlite3

import numpy as np
import pandas as pd
import pytest

from gabi import capital_input_audit as audit

ENTITY = "cik:0000000001"


def filing(accn="0000000001-24-000001", period="2023-12-31", filed="2024-02-15", form="10-K"):
    return {"accn": accn, "period": period, "filed_date": filed, "accepted": filed + " 16:00:00.0",
            "cik": ENTITY[4:], "form": form, "fp": "FY", "fy": "2023", "source_url": "https://www.sec.gov/test.zip"}


def fact(key, value, *, start="2023-01-01", end="2023-12-31", metadata=None):
    selected = metadata or filing()
    result = {"tag": audit.TAGS[key], "unit": "shares" if key == "shares" else "USD",
              "start_date": "" if key == "shares" else start, "end_date": end, "val": value,
              "filed_date": selected["filed_date"], "form": selected["form"], "fp": "FY", "fy": 2023,
              "accn": selected["accn"]}
    return {**result, "entity_id": ENTITY, "source_url": f"https://data.sec.gov/api/xbrl/companyfacts/CIK{ENTITY[4:]}.json",
            "payload_sha256": audit.frozen.fingerprint(result)}


def annual(records, *, filings=None, day="2024-07-02"):
    filings = pd.DataFrame(filings or [filing()])
    grouped = {}
    for row in records:
        grouped.setdefault((ENTITY, row["accn"]), []).append(row)
    return audit.annual_row(ENTITY, day, filings, grouped)


def test_same_period_cash_options_and_fcf_preserve_reported_zeros():
    row, used = annual([fact("buybacks", 20.), fact("issuance", 0.), fact("options", 8.),
                        fact("ocf", 100.), fact("capex", 30.)])
    assert row["common_cash_difference_usd"] == 20
    assert row["issuance_status"] == "reported" and row["options_value"] == 8
    assert row["fcf_usd"] == 70 and len(used) == 5
    assert not row["total_net_payout_accredited"]  # options not assumed disjoint or already included


def test_missing_issuance_is_not_zero_and_quarter_is_not_annual():
    row, _ = annual([fact("buybacks", 20.), fact("issuance", 5., start="2023-10-01")])
    assert row["common_cash_difference_usd"] is None
    assert row["issuance_status"] == "no_annual_period"
    row, _ = annual([fact("options", 5.), fact("buybacks", 20.), fact("ocf", 100.)])
    assert row["common_cash_difference_usd"] is None and row["fcf_usd"] is None
    assert row["issuance_status"] == "missing"


def test_do_not_mix_periods_or_restatement_filings():
    row, _ = annual([fact("buybacks", 20.), fact("issuance", 5., start="2023-01-07")])
    assert row["cash_status"] == "period_mismatch"
    amendment = filing(accn="0000000001-24-000002", filed="2024-06-01", form="10-K/A")
    row, _ = annual([fact("buybacks", 20.), fact("issuance", 5.)], filings=[filing(), amendment])
    assert row["accn"] == amendment["accn"]
    assert row["cash_status"] == "missing_component"  # no older filing fallback


def test_cutoff_excludes_signal_day_future_and_late_acceptance():
    original = filing()
    future = filing(accn="0000000001-24-000003", filed="2024-07-02", form="10-K/A")
    row, _ = annual([fact("buybacks", 20.), fact("issuance", 5.)], filings=[original, future])
    assert row["accn"] == original["accn"] and row["common_cash_difference_usd"] == 15
    future["filed_date"] = "2024-07-01"
    future["accepted"] = "2024-07-02 08:00:00.0"
    chosen, _ = audit.latest_annual(pd.DataFrame([original, future]), "2024-07-02")
    assert chosen["accn"] == original["accn"]
    future["accepted"] = ""
    assert audit.latest_annual(pd.DataFrame([original, future]), "2024-07-02")[1] == "unknown_acceptance_date"


def test_duplicate_conflicts_bad_signs_and_infinite_values_are_not_repaired():
    row, _ = annual([fact("buybacks", 20.), fact("buybacks", 21.), fact("issuance", 5.)])
    assert row["buybacks_status"] == "conflicting_fact_or_period"
    row, used = annual([fact("buybacks", 20.), fact("buybacks", 20.), fact("issuance", 5.)])
    assert row["common_cash_difference_usd"] == 15 and len(used) == 2
    row, _ = annual([fact("buybacks", -20.), fact("issuance", 5.), fact("ocf", -10.), fact("capex", 3.)])
    assert row["buybacks_status"] == "invalid_value" and row["fcf_usd"] == -13
    invalid = fact("issuance", 1.)
    invalid["val"] = np.inf
    row, _ = annual([fact("buybacks", 20.), invalid])
    assert row["issuance_status"] == "invalid_value"


def test_expired_wrong_fiscal_year_and_metadata_do_not_fall_back():
    row, _ = annual([fact("buybacks", 20., end="2022-12-31"), fact("issuance", 5., end="2022-12-31")])
    assert row["common_cash_difference_usd"] is None
    bad = fact("buybacks", 20.)
    bad["filed_date"] = "2024-02-14"
    row, _ = annual([bad, fact("issuance", 5.)])
    assert row["buybacks_status"] == "metadata_mismatch"
    row, used = annual([fact("buybacks", 20.), fact("issuance", 5.)], day="2025-07-15")
    assert row["filing_status"] == "stale_annual_filing" and not used


def test_shares_use_same_filing_annual_balance_and_never_claim_split_adjustment():
    row, _ = annual([fact("shares", 400), fact("shares", 100, end="2022-12-31"),
                     fact("shares", 200, end="2023-09-30")])
    assert row["shares_change_raw"] == 3
    assert row["split_adjusted_dilution"] is None
    assert row["shares_status"] == "raw_comparative_split_basis_unverified"
    row, _ = annual([fact("shares", 100), fact("shares", 110, end="2023-09-30")])
    assert row["shares_status"] == "missing_prior_balance"


def test_sample_size_deduplicates_share_classes_and_is_not_performance():
    rows = []
    for day in pd.date_range("2011-07-01", periods=57, freq="QS"):
        row, _ = annual([fact("buybacks", 20.), fact("issuance", 5.)])
        for i in range(29):
            rows.append({**row, "entity_id": f"cik:{i:010}", "fecha": day.strftime("%Y-%m-%d"), "division": "D"})
        rows.append(rows[-1].copy())  # second class is not company #30
    panel = pd.DataFrame(rows)
    covered = audit.coverage(panel).query("stratum == 'all'")
    assert covered.n_cash_pair.eq(29).all() and covered.n_universe.eq(30).all()
    result = audit.summary(panel)
    assert not result["viability"]["n_cash_pair"]["sample_size_gate"]
    assert not result["performance_analysis"] and not result["split_adjusted_dilution_accredited"]


def test_readonly_snapshot_hash_entity_and_provenance_guards(tmp_path):
    snapshot = tmp_path / "snapshot.db"
    raw = fact("buybacks", 20.)
    payload = {key: value for key, value in raw.items() if key not in {"entity_id", "source_url", "payload_sha256"}}
    with sqlite3.connect(snapshot) as connection:
        connection.execute("CREATE TABLE entity_observations(entity_id TEXT,dataset TEXT,symbol TEXT,record_key TEXT,payload_json TEXT,source TEXT)")
        connection.execute("INSERT INTO entity_observations VALUES (?, 'edgar_facts', 'X', '1', ?, ?)",
                           (ENTITY, json.dumps(payload), raw["source_url"]))
    before = snapshot.read_bytes()
    digest = audit.frozen.file_hash(snapshot)
    actual, source = audit.read_facts(snapshot, digest, {ENTITY})
    assert actual[(ENTITY, raw["accn"])][0]["val"] == 20
    assert source["fact_rows"] == 1 and snapshot.read_bytes() == before
    assert not audit.read_facts(snapshot, digest, {"cik:0000000002"})[0]
    with pytest.raises(ValueError, match="Snapshot"):
        audit.read_facts(snapshot, "wrong", {ENTITY})
    with sqlite3.connect(snapshot) as connection:
        connection.execute("UPDATE entity_observations SET source='https://data.sec.gov/api/xbrl/companyfacts/CIK0000000002.json'")
    with pytest.raises(ValueError, match="CIK"):
        audit.read_facts(snapshot, audit.frozen.file_hash(snapshot), {ENTITY})


def test_preregister_and_overwrite_guards(tmp_path, monkeypatch):
    monkeypatch.setattr(audit, "OUTPUT", tmp_path)
    (tmp_path / "PROTOCOLO.md").write_text("protocol\n", encoding="utf-8")
    with pytest.raises(ValueError, match="preregistro"):
        audit.verify()
    assert audit.preregister() == audit.preregister()
    audit.save_json(tmp_path / "resultado.json", {})
    with pytest.raises(ValueError, match="congelada"):
        audit.analyze(tmp_path)
    (tmp_path / "PROTOCOLO.md").write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="protocolo"):
        audit.preregister()


def test_complete_audit_verifies_reproduces_and_rejects_tampering(tmp_path, monkeypatch):
    monkeypatch.setattr(audit, "OUTPUT", tmp_path)
    monkeypatch.setattr(audit, "RANKINGS", tmp_path)
    (tmp_path / "PROTOCOLO.md").write_text("protocol\n", encoding="utf-8")
    (tmp_path / "snapshot.db").write_bytes(b"test-only snapshot")
    snapshot_hash = audit.frozen.file_hash(tmp_path / "snapshot.db")
    audit.save_json(tmp_path / "manifest.json", {"snapshot_sha256": snapshot_hash})
    frames = {day.strftime("%Y-%m-%d"): pd.DataFrame({"entity_id": [ENTITY], "division": ["D"]}, index=["X"])
              for day in pd.date_range("2011-07-01", periods=57, freq="QS")}
    monkeypatch.setattr(audit, "universe", lambda: (frames, {"test": "test-only"}))
    filings = pd.DataFrame([filing()])
    monkeypatch.setattr(audit, "filing_periods", lambda ciks: (filings.copy(), {}))
    facts = {(ENTITY, filing()["accn"]): [fact("buybacks", 20.), fact("issuance", 5.), fact("ocf", 100.), fact("capex", 30.)]}
    monkeypatch.setattr(audit, "read_facts", lambda *args: (facts, {"snapshot_sha256": snapshot_hash}))
    result = audit.analyze(tmp_path)
    assert result == audit.verify()
    assert result == audit.analyze(tmp_path / "reproduction")
    published = tmp_path / "annual_inputs.csv"
    published.write_text(published.read_text(encoding="utf-8") + "tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="Artefacto modificado"):
        audit.verify()
