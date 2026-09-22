import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gabi import app_mode, blind_validation, config, research_lab, storage


def _isolate_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    monkeypatch.setattr(app_mode, "MODE_PATH", tmp_path / "app_mode.json")


def _seed_prices(dates, symbol_closes):
    for symbol, closes in symbol_closes:
        storage.upsert_prices(symbol, pd.DataFrame({"Open": closes, "High": closes,
            "Low": closes, "Close": closes, "Adj Close": closes, "Volume": [1] * len(closes)}, index=dates))


def _fake_ranking(monkeypatch, scores: dict):
    def _rank(day, symbols=None):
        syms = list(scores)
        table = pd.DataFrame({"composite_score": [scores[s] for s in syms],
                              "score_coverage": [.9] * len(syms)}, index=syms)
        return {"table": table}
    monkeypatch.setattr(blind_validation.screener_asof, "build_ranking_as_of", _rank)


def _create_and_record_validation(monkeypatch, weights, *, as_of="2024-01-10", unlock="2099-01-01"):
    dates = pd.date_range("2024-01-01", periods=10, freq="D")
    _seed_prices(dates, [("A", [100.0] * 10), ("B", [50.0] * 10)])
    _fake_ranking(monkeypatch, {"A": 90, "B": 80})
    vid = blind_validation.create_validation("Test", weights, 2, 3, as_of, unlock)
    blind_validation.record_rebalance(vid, as_of=as_of)
    return vid


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


def test_current_model_status_detects_live_forward_from_locked_blind_validation(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    config.save_weights(dict(app_mode.FROZEN_WEIGHTS))
    vid = _create_and_record_validation(monkeypatch, dict(app_mode.FROZEN_WEIGHTS))

    result = app_mode.current_model_status()
    assert result["status"] == "LIVE_FORWARD"
    assert result["live_forward_source"] == "blind_validation"
    assert result["blind_validation_id"] == vid


def test_current_model_status_ignores_blind_validation_without_recorded_periods(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    config.save_weights(dict(app_mode.FROZEN_WEIGHTS))
    blind_validation.create_validation("Sin rebalanceos", dict(app_mode.FROZEN_WEIGHTS), 2, 3,
                                       "2024-01-10", "2099-01-01")

    result = app_mode.current_model_status()
    assert result["status"] == "VALIDATED"
    assert result["live_forward_source"] is None
    assert result["blind_validation_id"] is None


def test_current_model_status_ignores_blind_validation_with_different_weights(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    config.save_weights(dict(app_mode.FROZEN_WEIGHTS))
    other_weights = {"value": 0.5, "quality": 0.2, "momentum": 0.2, "risk": 0.1}
    _create_and_record_validation(monkeypatch, other_weights)

    result = app_mode.current_model_status()
    assert result["status"] == "VALIDATED"
    assert result["blind_validation_id"] is None


def test_current_model_status_ignores_broken_early_blind_validation(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    config.save_weights(dict(app_mode.FROZEN_WEIGHTS))
    vid = _create_and_record_validation(monkeypatch, dict(app_mode.FROZEN_WEIGHTS))
    blind_validation.break_seal_early(vid, "prueba de que no cuenta")

    result = app_mode.current_model_status()
    assert result["status"] == "VALIDATED"
    assert result["blind_validation_id"] is None


def test_current_model_status_blind_validation_signal_wins_over_research_lab_source_label(tmp_path, monkeypatch):
    """Ambas señales pueden estar activas a la vez -- el resultado sigue
    siendo LIVE_FORWARD, y la fuente mostrada es la fuerte (blind_validation)."""
    _isolate_db(tmp_path, monkeypatch)
    config.save_weights(dict(app_mode.FROZEN_WEIGHTS))
    vid = _create_and_record_validation(monkeypatch, dict(app_mode.FROZEN_WEIGHTS))
    research_lab.log_experiment("GABI-MF-v1", "LIVE_FORWARD", True, sharpe=0.5)

    result = app_mode.current_model_status()
    assert result["status"] == "LIVE_FORWARD"
    assert result["live_forward_source"] == "blind_validation"
    assert result["blind_validation_id"] == vid


def test_current_model_status_still_detects_research_lab_signal_without_blind_validation(tmp_path, monkeypatch):
    _isolate_db(tmp_path, monkeypatch)
    config.save_weights(dict(app_mode.FROZEN_WEIGHTS))
    research_lab.log_experiment("GABI-MF-v1", "LIVE_FORWARD", True, sharpe=0.5)

    result = app_mode.current_model_status()
    assert result["status"] == "LIVE_FORWARD"
    assert result["live_forward_source"] == "research_lab"
    assert result["blind_validation_id"] is None
