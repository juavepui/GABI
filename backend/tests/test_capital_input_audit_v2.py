"""Quarantine preserves provenance and blocks mixed filings without legacy changes."""

import json
import sqlite3

import pandas as pd
import pytest

from gabi import capital_input_audit_v2 as audit

ENTITY = "cik:0000000001"
URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK0000000001.json"


def snapshot_file(root, entries):
    snapshot = root / "snapshot.db"
    with sqlite3.connect(snapshot) as connection:
        connection.execute("CREATE TABLE entity_observations(entity_id TEXT,dataset TEXT,symbol TEXT,record_key TEXT,payload_json TEXT,source TEXT)")
        for i, (tag, accn, source) in enumerate(entries):
            payload = {"tag": tag, "accn": accn, "val": float(i + 1), "unit": "USD", "start_date": "2023-01-01",
                       "end_date": "2023-12-31", "form": "10-K", "fp": "FY", "fy": 2023, "filed_date": "2024-02-15"}
            connection.execute("INSERT INTO entity_observations VALUES (?,'edgar_facts','X',?,?,?)",
                               (ENTITY, str(i), json.dumps(payload), source))
    return snapshot


def test_quarantine_blocks_mixed_filings_keeps_evidence_and_readonly(tmp_path):
    snapshot = snapshot_file(tmp_path, [(audit.base.TAGS["buybacks"], "A", URL),
        (audit.base.TAGS["issuance"], "A", "https://www.sec.gov/Archives/edgar/data/1/x/original.xml"),
        (audit.base.TAGS["buybacks"], "B", URL), (audit.base.TAGS["issuance"], "B", URL)])
    before = snapshot.read_bytes()
    facts, source, quarantine, blocked = audit.read_facts(snapshot, audit.base.frozen.file_hash(snapshot), {ENTITY})
    assert (ENTITY, "A") not in facts and (ENTITY, "A") in blocked
    assert len(facts[(ENTITY, "B")]) == 2
    assert source["fact_rows"] == 4 and source["usable_source_rows"] == 2
    assert source["mixed_source_filings_blocked"] == 1
    assert quarantine.iloc[0].source_reason == "unsupported_SEC_instance_source"
    assert quarantine.iloc[0].val == 2 and snapshot.read_bytes() == before


def test_wrong_issuer_source_cannot_enter_admitted_subset(tmp_path):
    snapshot = snapshot_file(tmp_path, [(audit.base.TAGS["buybacks"], "A", URL.replace("0000000001", "0000000002"))])
    facts, _, quarantine, blocked = audit.read_facts(snapshot, audit.base.frozen.file_hash(snapshot), {ENTITY})
    assert not facts and blocked == {(ENTITY, "A")}
    assert quarantine.iloc[0].source_reason == "source_not_matching_CIK_CompanyFacts"
    with pytest.raises(ValueError, match="Snapshot"):
        audit.read_facts(snapshot, "wrong", {ENTITY})


def test_original_engine_dependency_is_pinned(tmp_path, monkeypatch):
    monkeypatch.setattr(audit, "OUTPUT", tmp_path)
    monkeypatch.setattr(audit, "BASE_SHA256", "wrong")
    with pytest.raises(ValueError, match="original"):
        audit.preregister()


def test_end_to_end_quarantine_has_no_fallback_and_reproduces(tmp_path, monkeypatch):
    monkeypatch.setattr(audit, "OUTPUT", tmp_path)
    monkeypatch.setattr(audit.base, "RANKINGS", tmp_path)
    (tmp_path / "PROTOCOLO.md").write_text("revision2\n", encoding="utf-8")
    # Base protocol path remains real and is read only; its engine stays pinned.
    snapshot = snapshot_file(tmp_path, [(audit.base.TAGS["buybacks"], "0000000001-24-000001", URL),
        (audit.base.TAGS["issuance"], "0000000001-24-000001", "https://www.sec.gov/Archives/edgar/data/1/x/original.xml")])
    audit.base.save_json(tmp_path / "manifest.json", {"snapshot_sha256": audit.base.frozen.file_hash(snapshot)})
    frames = {"2024-07-02": pd.DataFrame({"entity_id": [ENTITY], "division": ["D"]}, index=["X"])}
    monkeypatch.setattr(audit.base, "universe", lambda: (frames, {"test": "test-only"}))
    metadata = {"accn": "0000000001-24-000001", "period": "2023-12-31", "filed_date": "2024-02-15",
                "accepted": "2024-02-15 16:00:00.0", "cik": ENTITY[4:], "form": "10-K", "fp": "FY", "fy": "2023", "source_url": "https://www.sec.gov/test.zip"}
    filings = pd.DataFrame([metadata])
    monkeypatch.setattr(audit.base, "filing_periods", lambda ciks: (filings.copy(), {}))
    result = audit.analyze(tmp_path)
    panel = pd.read_csv(tmp_path / "annual_inputs.csv")
    assert panel.iloc[0].cash_status == "source_quarantined"
    assert panel.common_cash_difference_usd.isna().all()
    assert result == audit.verify() == audit.analyze(tmp_path / "reproduce")
    assert result["summary"]["selected_filing_source_status"] == {"quarantined_filing": 1}
    assert not result["new_strategy_configurations"]
    path = tmp_path / "source_quarantine.csv"
    path.write_text(path.read_text(encoding="utf-8") + "tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="Artefacto"):
        audit.verify()
