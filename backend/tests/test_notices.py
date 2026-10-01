"""Home notices of the old portada: blind rebalances due within a week and the #44 analysis state."""

from datetime import date

from fastapi.testclient import TestClient

from gabi import config
from gabi.application.administration.notices import Notices
from gabi.application.errors import QueryError
from gabi.infrastructure.settings import Settings
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
