from datetime import UTC, datetime

from streamlit.testing.v1 import AppTest

from gabi import live_ledger


def render():
    return AppTest.from_string('from gabi import live_ledger_ui\nlive_ledger_ui.render()').run()


def test_viewing_empty_ledger_does_not_create_a_decision():
    app = render()
    assert not app.exception
    assert "Aún no hay" in app.info[0].value
    assert live_ledger.events() == []


def test_historical_phase_excluded_and_evaluation_appended_separately(monkeypatch):
    from test_live_ledger import payload

    monkeypatch.setattr(live_ledger, "_now", lambda: datetime(2024, 1, 10, 22, tzinfo=UTC))
    historical = live_ledger.append_decision(payload(), stage="RETROSPECTIVE")
    app = render()
    assert not app.exception and not app.button
    assert any("históricos/OOS" in i.value for i in app.info)
    live_ledger.append_decision(payload("DEGRADED", []))
    app = render()
    assert not app.exception
    app.button[0].click().run()
    assert not app.exception
    assert live_ledger.events()[0] == historical
    assert live_ledger.events()[-1]["payload"]["kind"] == "EVALUATION"


def test_corrupt_anchor_is_visible_and_disables_reporting():
    live_ledger.anchor_path().parent.mkdir(parents=True, exist_ok=True)
    live_ledger.anchor_path().write_text('{"seq":99,"hash":"deleted"}')
    app = render()
    assert not app.exception
    assert "no íntegro" in app.error[0].value
    assert not app.button
