"""Home notices of the old portada: blind rebalances due within a week and the #44 analysis state."""

from datetime import UTC, date, datetime

from fastapi.testclient import TestClient

from gabi import config, live_ledger
from gabi.application.administration.notices import Notices
from gabi.application.errors import QueryError
from gabi.infrastructure.settings import Settings
from gabi.infrastructure.storage.live_ledger import SqliteLiveLedger
from gabi.infrastructure.storage.smallmid import SmallmidFiles
from gabi_api.bootstrap import create_app

TODAY = date(2026, 10, 1)


class Blind:
    def __init__(self, items=None, error=False):
        self.items, self.error = items or [], error

    def list_status(self):
        if self.error:
            raise QueryError("blind_data_invalid", "x", 503)
        return {"items": self.items}


def _item(vid, status, due):
    return {"id": vid, "name": f"prueba {vid}", "status": status, "next_rebalance_due": due}


def test_only_locked_validations_due_within_seven_days_or_overdue(tmp_path):
    blind = Blind([_item(1, "locked", "2026-10-08"), _item(2, "locked", "2026-10-09"),
                   _item(3, "locked", "2026-09-20"), _item(4, "unlocked", "2026-10-02")])
    smallmid = SmallmidFiles(tmp_path, tmp_path, lambda: "2027-01-15")
    result = Notices(blind, smallmid, lambda: TODAY).current()
    assert [(row["id"], row["days"], row["overdue"]) for row in result["blind_rebalances"]] == [
        (1, 7, False), (3, -11, True)]
    assert result["smallmid"] == {"data_frozen": False, "tiingo_complete": False,
                                  "freeze_deadline": "2027-01-15", "analyzed": False}


def test_smallmid_freezes_at_the_deadline_or_when_tiingo_completes_and_reports_the_analysis(tmp_path):
    files = SmallmidFiles(tmp_path / "data", tmp_path, lambda: "2027-01-15")
    assert files.state(date(2027, 1, 15))["data_frozen"] is True
    (tmp_path / "data" / "smallmid_test").mkdir(parents=True)
    (tmp_path / "data" / "smallmid_test" / "tiingo_completa.json").write_text("{}")
    assert files.state(TODAY)["data_frozen"] is True
    (tmp_path / "docs" / "smallmid-test").mkdir(parents=True)
    (tmp_path / "docs" / "smallmid-test" / "resultado.json").write_text("{}")
    assert files.state(TODAY)["analyzed"] is True


def test_a_failing_blind_store_hides_its_notice_without_breaking_the_home(tmp_path):
    result = Notices(Blind(error=True), SmallmidFiles(tmp_path, tmp_path, lambda: "2027-01-15"),
                     lambda: TODAY).current()
    assert result["blind_rebalances"] == [] and result["blind_available"] is False


def test_notices_endpoint_reads_without_writing(tmp_path):
    with TestClient(create_app(Settings(config.DATA_DIR), today=lambda: TODAY)) as client:
        before = sorted(path.name for path in config.DATA_DIR.iterdir())
        response = client.get("/api/v1/notices")
        assert sorted(path.name for path in config.DATA_DIR.iterdir()) == before
    assert response.status_code == 200
    assert response.json()["blind_rebalances"] == [] and response.json()["smallmid"]["freeze_deadline"] == "2027-01-15"
    # No ledger yet: the follow-up never ran, and reading it created nothing (#290).
    assert response.json()["periodic"]["status"] == "never"


def test_periodic_notice_reports_the_newest_working_decision_and_hides_on_read_errors(tmp_path):
    smallmid = SmallmidFiles(tmp_path, tmp_path, lambda: "2027-01-15")
    working = {"created_at": "2026-09-25T21:30:00+00:00", "status": "SIGNAL", "model_id": "GABI-MF-v2"}
    result = Notices(Blind(), smallmid, lambda: TODAY, lambda: (working, working)).current()
    assert result["periodic"]["status"] == "late" and result["periodic"]["business_days"] == 4

    def unreadable():
        raise OSError("locked")
    assert Notices(Blind(), smallmid, lambda: TODAY, unreadable).current()["periodic"] is None
    assert Notices(Blind(), smallmid, lambda: TODAY).current()["periodic"] is None


def test_ledger_summary_reads_only_three_fields_of_the_newest_decisions(monkeypatch):
    reader = SqliteLiveLedger(config.DATA_DIR)
    assert reader.last_decisions() == (None, None)
    now = datetime(2024, 1, 10, 22, tzinfo=UTC)
    base = {"model_id": "GABI-MF-v1", "model_version": "m", "config_version": "c", "market_date": "2024-01-10",
            "top_n": [], "sources": {}, "data_fingerprint": "f", "git_commit": "g",
            "configuration": {"weights": {}}}
    monkeypatch.setattr(live_ledger, "_now", lambda: now)
    live_ledger.append_decision({**base, "status": "SIGNAL"})
    live_ledger.append_decision({**base, "model_id": "GABI-MF-v2", "status": "ERROR"})
    last, working = reader.last_decisions()
    assert last == {"created_at": now.isoformat(), "status": "ERROR", "model_id": "GABI-MF-v2"}
    assert working == {"created_at": now.isoformat(), "status": "SIGNAL", "model_id": "GABI-MF-v1"}
