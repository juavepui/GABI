import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gabi import app_mode, config, research_lab


def _isolate_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    monkeypatch.setattr(app_mode, "MODE_PATH", tmp_path / "app_mode.json")


def test_default_mode_is_investor_without_saved_file(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    assert app_mode.get_mode() == "INVESTOR"


def test_set_mode_persists_across_calls(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    app_mode.set_mode("RESEARCH")
    assert app_mode.get_mode() == "RESEARCH"
    app_mode.set_mode("INVESTOR")
    assert app_mode.get_mode() == "INVESTOR"


def test_set_mode_rejects_unknown_value(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    try:
        app_mode.set_mode("ADMIN")
        assert False, "debía lanzar ValueError"
    except ValueError:
        pass


def test_get_mode_falls_back_to_default_on_corrupt_file(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    app_mode.MODE_PATH.parent.mkdir(parents=True, exist_ok=True)
    app_mode.MODE_PATH.write_text("{ esto no es json valido")
    assert app_mode.get_mode() == "INVESTOR"


def test_weights_match_frozen_exact():
    assert app_mode.weights_match_frozen(dict(app_mode.FROZEN_WEIGHTS)) is True


def test_weights_match_frozen_within_tolerance():
    tweaked = {k: v + 1e-9 for k, v in app_mode.FROZEN_WEIGHTS.items()}
    assert app_mode.weights_match_frozen(tweaked) is True


def test_weights_match_frozen_false_for_any_deviation():
    tweaked = dict(app_mode.FROZEN_WEIGHTS)
    tweaked["value"] += 0.01
    assert app_mode.weights_match_frozen(tweaked) is False


def test_weights_match_frozen_false_for_empty_or_missing_key():
    assert app_mode.weights_match_frozen({}) is False
    partial = {k: v for k, v in app_mode.FROZEN_WEIGHTS.items() if k != "risk"}
    assert app_mode.weights_match_frozen(partial) is False  # "risk" ausente cuenta como 0.0, no coincide


def test_model_status_frozen_weights_without_live_forward_is_validated():
    assert app_mode.model_status(dict(app_mode.FROZEN_WEIGHTS)) == "VALIDATED"


def test_model_status_frozen_weights_with_live_forward_is_live_forward():
    assert app_mode.model_status(dict(app_mode.FROZEN_WEIGHTS), live_forward_active=True) == "LIVE_FORWARD"


def test_model_status_any_deviation_is_experimental_even_with_live_forward_flag():
    tweaked = {**app_mode.FROZEN_WEIGHTS, "value": 0.5}
    assert app_mode.model_status(tweaked, live_forward_active=True) == "EXPERIMENTAL"


def test_current_model_status_reads_saved_weights_and_defaults_safely(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    config.save_weights(dict(app_mode.FROZEN_WEIGHTS))
    result = app_mode.current_model_status()
    assert result["status"] == "VALIDATED"
    assert result["matches_frozen"] is True
    assert result["model_id"] == app_mode.FROZEN_MODEL_ID


def test_current_model_status_detects_live_forward_experiment(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    config.save_weights(dict(app_mode.FROZEN_WEIGHTS))
    research_lab.log_experiment("GABI-MF-v1", "LIVE_FORWARD", True, sharpe=0.5)
    result = app_mode.current_model_status()
    assert result["status"] == "LIVE_FORWARD"


def test_current_model_status_experimental_for_custom_weights(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    config.save_weights({"value": 0.5, "quality": 0.2, "momentum": 0.2, "risk": 0.1})
    result = app_mode.current_model_status()
    assert result["status"] == "EXPERIMENTAL"
    assert result["matches_frozen"] is False
    assert result["model_id"] == "EXPERIMENTAL"


ALL_PAGES = [
    "pages/7_Aprender.py", "pages/1_Screener.py", "pages/2_Ficha_Empresa.py",
    "pages/6_Comparar_Empresas.py", "pages/8_Ranking_Historico.py", "pages/11_Research_Lab.py",
    "pages/12_Factor_Lab.py", "pages/13_Blind_Validation.py", "pages/14_Portfolio_Lab.py",
    "pages/9_Decisiones.py", "pages/10_Carteras_Simuladas.py", "pages/5_Panel_Macro.py",
    "pages/4_Diario_Inversion.py", "pages/15_Salud_Datos.py", "pages/16_Signal_Monitor.py",
    "pages/3_Configuracion.py",
]


def test_visible_pages_research_mode_sees_everything():
    assert app_mode.visible_pages("RESEARCH", ALL_PAGES) == ALL_PAGES


def test_visible_pages_investor_mode_excludes_research_tools():
    visible = app_mode.visible_pages("INVESTOR", ALL_PAGES)
    for research_only in ("pages/8_Ranking_Historico.py", "pages/11_Research_Lab.py",
                          "pages/12_Factor_Lab.py", "pages/13_Blind_Validation.py",
                          "pages/14_Portfolio_Lab.py"):
        assert research_only not in visible
    for essential in ("pages/1_Screener.py", "pages/2_Ficha_Empresa.py", "pages/9_Decisiones.py",
                      "pages/4_Diario_Inversion.py", "pages/15_Salud_Datos.py", "pages/16_Signal_Monitor.py"):
        assert essential in visible


def test_visible_pages_preserves_input_order():
    visible = app_mode.visible_pages("INVESTOR", ALL_PAGES)
    assert visible == [p for p in ALL_PAGES if p in app_mode.INVESTOR_PAGES]


def test_visible_pages_rejects_unknown_mode():
    try:
        app_mode.visible_pages("ADMIN", ALL_PAGES)
        assert False, "debía lanzar ValueError"
    except ValueError:
        pass


def test_experimental_banner_none_for_frozen_weights():
    assert app_mode.experimental_banner_message(dict(app_mode.FROZEN_WEIGHTS)) is None


def test_experimental_banner_present_and_mentions_deviation():
    tweaked = {"value": 0.5, "quality": 0.2, "momentum": 0.2, "risk": 0.1}
    message = app_mode.experimental_banner_message(tweaked)
    assert message is not None
    assert "EXPERIMENTAL" in message
    assert "Research Lab" in message
