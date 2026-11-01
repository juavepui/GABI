"""NSI-v1 data gate (#252): issuance from one 10-K, the restatement audit and the gate, without returns."""

import math
from datetime import date

import pytest

from gabi.application.errors import QueryError
from gabi.application.research import cbop_coverage, net_issuance_gate
from gabi.domain.research import net_issuance as nsi

TAG = "WeightedAverageNumberOfSharesOutstandingBasic"
SIGNAL = date(2024, 7, 1)


def entry(val, year, filed, accn, form="10-K", tag=TAG):
    return tag, {"val": val, "start": f"{year}-01-01", "end": f"{year}-12-31", "filed": filed, "accn": accn,
                 "form": form, "fp": "FY"}


def facts(*items) -> dict:
    families: dict = {}
    for tag, item in items:
        families.setdefault(tag, {"units": {"shares": []}})["units"]["shares"].append(item)
    return {"facts": {"us-gaap": families}}


def filing(year, current, comparative, accn, filed=None, **extra):
    filed = filed or f"{year + 1}-02-15"
    return [entry(current, year, filed, accn, **extra), entry(comparative, year - 1, filed, accn, **extra)]


def test_issuance_is_the_log_change_inside_one_10k_and_reconciles_with_the_previous_one():
    value = nsi.issuance(facts(*filing(2022, 100.0, 98.0, "a22"), *filing(2023, 104.0, 100.0, "a23")), SIGNAL)
    assert value.state == "computed" and value.value == pytest.approx(math.log(1.04))
    assert value.anchor == "2023-12-31" and value.accession == "a23" and value.check == "reconciled"


def test_a_split_restates_the_comparative_figure_and_still_reconciles():
    # Filing 2022 reported 100; after a 2-for-1 split, filing 2023 restates 2022 as 200.
    value = nsi.issuance(facts(*filing(2022, 100.0, 98.0, "a22"), *filing(2023, 206.0, 200.0, "a23")), SIGNAL)
    assert value.check == "split_restated" and value.value == pytest.approx(math.log(1.03))
    odd = nsi.issuance(facts(*filing(2022, 100.0, 98.0, "a22"), *filing(2023, 120.0, 117.0, "a23")), SIGNAL)
    assert odd.check == "mismatch"


def test_only_original_10ks_filed_before_the_signal_count():
    late = filing(2023, 104.0, 100.0, "a23", filed="2024-07-01")
    value = nsi.issuance(facts(*filing(2022, 100.0, 98.0, "a22"), *late), SIGNAL)
    assert value.anchor == "2022-12-31" and value.check == "no_previous_filing"
    amended = filing(2023, 104.0, 100.0, "a23x", form="10-K/A")
    assert nsi.issuance(facts(*amended), SIGNAL).reason == "no_annual_report"


def test_missing_comparative_conflicts_and_stale_reports_are_not_computed():
    alone = [entry(104.0, 2023, "2024-02-15", "a23")]
    assert nsi.issuance(facts(*alone), SIGNAL).reason == "no_comparative_year"
    conflict = [*filing(2023, 104.0, 100.0, "a23"), entry(101.0, 2022, "2024-02-15", "a23")]
    assert nsi.issuance(facts(*conflict), SIGNAL).reason == "no_comparative_year"
    assert nsi.issuance(facts(*filing(2022, 100.0, 98.0, "a22")), date(2025, 7, 10)).reason == "annual_report_too_old"
    other_tag = filing(2023, 104.0, 100.0, "a23", tag="WeightedAverageNumberOfSharesOutstandingBasicAndDiluted")
    assert nsi.issuance(facts(*other_tag), SIGNAL).state == "computed"


def test_the_gate_needs_coverage_and_reconciliation_and_never_reads_reserved_dates():
    good = facts(*filing(2022, 100.0, 98.0, "a22"), *filing(2023, 104.0, 100.0, "a23"))
    bad = facts(*filing(2022, 100.0, 98.0, "a22"), *filing(2023, 120.0, 117.0, "a23"))
    stored = {"1": good, "2": good, "3": bad}
    members = {SIGNAL: {"A": "1", "B": "2", "C": "3", "D": None}}
    report = net_issuance_gate.audit(members, facts=stored.__getitem__)
    row = report["signals"][0]
    assert (row["members"], row["computed"], row["audited"], row["reconciled"]) == (4, 3, 3, 2)
    assert row["coverage"] == pytest.approx(0.75) and not row["passes"]  # 2/3 reconciled < 90 %.
    assert report["examples"]["2024-07-01"] == {"missing": ["D:identity_unresolved"], "mismatch": ["C"]}
    assert report["decision"] == "close_unfeasible" and report["returns_read"] is False
    clean = net_issuance_gate.audit({SIGNAL: {"A": "1", "B": "2", "C": "1"}}, facts=stored.__getitem__)
    assert clean["passes"] and clean["decision"] == "continue_to_exploratory"
    with pytest.raises(QueryError):
        net_issuance_gate.audit({date(2025, 7, 3): {"A": "1"}}, facts=lambda cik: pytest.fail("read"))


def test_the_download_keeps_share_counts_under_their_own_tag_fingerprint(tmp_path):
    from gabi.infrastructure.storage.cbop_facts import SqliteCbopFacts

    store = SqliteCbopFacts(tmp_path / "nsi" / "facts.db")
    payload = facts(*filing(2023, 104.0, 100.0, "a23"))
    payload["facts"]["us-gaap"]["Assets"] = {"units": {"USD": [{"val": 1.0, "end": "2023-12-31", "accn": "a23"}]}}
    cbop_coverage.download(["1"], done=set(), save=store.save, tags=net_issuance_gate.TAGS,
                           companyfacts=lambda cik: payload, submissions=lambda cik: {}, now=lambda: "t")
    assert set(store.facts("1")["facts"]["us-gaap"]) == {TAG}
    assert store.downloaded(cbop_coverage.tags_sha256(net_issuance_gate.TAGS)) == {"1": "ok"}
    assert store.downloaded(cbop_coverage.tags_sha256()) == {}
    assert nsi.issuance(store.facts("1"), SIGNAL).value == pytest.approx(math.log(1.04))
