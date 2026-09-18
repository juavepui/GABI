import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gabi import config, factor_lab as fl, storage


def _seed_prices(dates, symbol_closes):
    for symbol, closes in symbol_closes:
        storage.upsert_prices(symbol, pd.DataFrame({"Open": closes, "High": closes,
            "Low": closes, "Close": closes, "Adj Close": closes, "Volume": [1] * len(closes)}, index=dates))


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gabi.db")
    monkeypatch.setattr(fl, "_MIN_ROWS_PER_QUANTILE", 1)  # datos sinteticos pequenos en los tests


def _fake_universe(symbols):
    return lambda day: {"is_exact": True, "symbols": symbols, "note": ""}


def _fake_ranking(scores: dict, sectors: dict = None):
    """scores: {symbol: valor} -- igual para todas las fechas del test (los
    tests de este archivo usan un unico rebalanceo salvo el de turnover)."""
    def _rank(day, symbols):
        table = pd.DataFrame({
            "composite_score": [scores[s] for s in symbols],
            "score_coverage": [.9] * len(symbols),
            "sector": [sectors.get(s, "Tech") if sectors else "Tech" for s in symbols],
        }, index=symbols)
        return {"table": table}
    return _rank


def test_rejects_validation_mode_with_max_symbols():
    with pytest.raises(ValueError, match="validation"):
        fl.run_factor_analysis("2024-01-02", "2024-02-02", mode="validation", max_symbols=50)


def test_rejects_fast_dev_mode_without_max_symbols():
    with pytest.raises(ValueError, match="fast_dev"):
        fl.run_factor_analysis("2024-01-02", "2024-02-02", mode="fast_dev", max_symbols=None)


def test_rejects_n_quantiles_below_two():
    with pytest.raises(ValueError):
        fl.run_factor_analysis("2024-01-02", "2024-02-02", max_symbols=10, mode="fast_dev", n_quantiles=1)


def test_perfect_predictor_gives_ic_near_one_and_positive_spread(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    symbols = ["A", "B", "C", "D", "E", "F"]
    dates = pd.date_range("2024-01-01", periods=45, freq="B")
    # Retorno futuro a 1 mes EXACTAMENTE en el mismo orden que el score: A peor, F mejor.
    for i, s in enumerate(symbols):
        start_price = 100.0
        end_price = 100.0 * (1 + 0.01 * (i + 1))  # A:+1%, B:+2%, ..., F:+6%
        closes = [start_price] * 20 + [end_price] * (len(dates) - 20)
        _seed_prices(dates, [(s, closes)])

    scores = {"A": 10, "B": 20, "C": 30, "D": 40, "E": 50, "F": 60}
    monkeypatch.setattr(fl.universe, "get_sp500_constituents_asof", _fake_universe(symbols))
    monkeypatch.setattr(fl.screener_asof, "build_ranking_as_of", _fake_ranking(scores))

    result = fl.run_factor_analysis("2024-01-02", "2024-02-02", months=1, max_symbols=len(symbols),
                                    mode="fast_dev", factor_cols=("composite_score",),
                                    horizons_months=(1,), n_quantiles=3)
    assert not result["skipped"]
    summary = result["summary"]
    row = summary[(summary["factor"] == "composite_score") & (summary["horizonte"] == 1)
                 & (~summary["sector_neutral"])].iloc[0]
    assert row["ic_mean"] == pytest.approx(1.0, abs=1e-6)
    assert row["q_spread"] > 0


def test_no_relationship_gives_ic_near_zero_on_average(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    symbols = ["A", "B", "C", "D", "E", "F"]
    dates = pd.date_range("2024-01-01", periods=45, freq="B")
    # El retorno NO tiene relacion con el orden del score (patron simetrico/no monotono).
    forward_pct = {"A": 0.03, "B": -0.02, "C": 0.05, "D": -0.04, "E": 0.01, "F": -0.01}
    for s in symbols:
        closes = [100.0] * 20 + [100.0 * (1 + forward_pct[s])] * (len(dates) - 20)
        _seed_prices(dates, [(s, closes)])

    scores = {"A": 10, "B": 20, "C": 30, "D": 40, "E": 50, "F": 60}
    monkeypatch.setattr(fl.universe, "get_sp500_constituents_asof", _fake_universe(symbols))
    monkeypatch.setattr(fl.screener_asof, "build_ranking_as_of", _fake_ranking(scores))

    result = fl.run_factor_analysis("2024-01-02", "2024-02-02", months=1, max_symbols=len(symbols),
                                    mode="fast_dev", factor_cols=("composite_score",),
                                    horizons_months=(1,), n_quantiles=3)
    row = result["summary"].iloc[0]
    assert abs(row["ic_mean"]) < 0.6  # lejos de +-1; no hay relacion monotona real


def test_turnover_is_zero_when_quantile_membership_is_identical(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    symbols = ["A", "B", "C", "D", "E", "F"]
    dates = pd.date_range("2024-01-01", periods=100, freq="B")
    for i, s in enumerate(symbols):
        closes = [100.0 * (1 + 0.01 * i)] * len(dates)  # precio plano, no afecta al turnover
        _seed_prices(dates, [(s, closes)])

    scores = {"A": 10, "B": 20, "C": 30, "D": 40, "E": 50, "F": 60}  # MISMO score en las 2 fechas
    monkeypatch.setattr(fl.universe, "get_sp500_constituents_asof", _fake_universe(symbols))
    monkeypatch.setattr(fl.screener_asof, "build_ranking_as_of", _fake_ranking(scores))

    result = fl.run_factor_analysis("2024-01-02", "2024-03-02", months=1, max_symbols=len(symbols),
                                    mode="fast_dev", factor_cols=("composite_score",),
                                    horizons_months=(1,), n_quantiles=3)
    turnover = result["turnover"]
    assert not turnover.empty
    assert turnover["turnover"].tolist() == pytest.approx([0.0] * len(turnover))


def test_turnover_is_one_when_quantile_membership_fully_changes(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    symbols = ["A", "B", "C", "D", "E", "F"]
    dates = pd.date_range("2024-01-01", periods=100, freq="B")
    for s in symbols:
        _seed_prices(dates, [(s, [100.0] * len(dates))])

    scores_by_date = {}

    def _rank(day, symbols):
        # rota los scores un tercio de vuelta entre la 1a y la 2a fecha -- cada
        # pareja de quantil pasa a otro quantil distinto, ninguna se queda fija
        # (una simple inversion deja el grupo central sin cambios, ver commit).
        if day not in scores_by_date:
            scores_by_date[day] = {"2024-01-02": {"A": 10, "B": 20, "C": 30, "D": 40, "E": 50, "F": 60},
                                   "2024-02-02": {"A": 30, "B": 40, "C": 50, "D": 60, "E": 10, "F": 20}}[day]
        scores = scores_by_date[day]
        table = pd.DataFrame({"composite_score": [scores[s] for s in symbols], "score_coverage": [.9] * len(symbols),
                              "sector": ["Tech"] * len(symbols)}, index=symbols)
        return {"table": table}

    monkeypatch.setattr(fl.universe, "get_sp500_constituents_asof", _fake_universe(symbols))
    monkeypatch.setattr(fl.screener_asof, "build_ranking_as_of", _rank)

    result = fl.run_factor_analysis("2024-01-02", "2024-03-02", months=1, max_symbols=len(symbols),
                                    mode="fast_dev", factor_cols=("composite_score",),
                                    horizons_months=(1,), n_quantiles=3)
    turnover = result["turnover"]
    assert not turnover.empty
    assert turnover["turnover"].tolist() == pytest.approx([1.0] * len(turnover))


def test_sector_neutral_filters_out_a_purely_sector_driven_signal(tmp_path, monkeypatch):
    """El score esta correlacionado SOLO con el sector (Tech puntua alto,
    Energy puntua bajo), sin ninguna relacion con nada especifico de cada
    empresa -- y ese trimestre Tech como sector sube mucho mas que Energy.
    El IC crudo debe salir artificialmente alto (capta el efecto sectorial);
    el IC sector-neutral debe salir cerca de 0 (lo filtra)."""
    _isolate(tmp_path, monkeypatch)
    tech = ["T1", "T2", "T3"]
    energy = ["E1", "E2", "E3"]
    symbols = tech + energy
    dates = pd.date_range("2024-01-01", periods=45, freq="B")
    # Tech sube mucho (sector en alza), Energy baja -- con una pequena variacion
    # IDIOSINCRATICA dentro de cada sector que NO seenlaza con el orden del score
    # (T1 tiene el score mas bajo de Tech pero el mejor retorno dentro de Tech, etc.)
    # -- si no hay ninguna variacion intra-sector, el IC neutral sale NaN (varianza 0),
    # no "cerca de 0".
    tech_end = {"T1": 112.0, "T2": 108.0, "T3": 110.0}
    energy_end = {"E1": 93.0, "E2": 97.0, "E3": 95.0}
    for s in tech:
        closes = [100.0] * 20 + [tech_end[s]] * (len(dates) - 20)
        _seed_prices(dates, [(s, closes)])
    for s in energy:
        closes = [100.0] * 20 + [energy_end[s]] * (len(dates) - 20)
        _seed_prices(dates, [(s, closes)])

    scores = {"T1": 80, "T2": 82, "T3": 84, "E1": 20, "E2": 22, "E3": 24}
    sectors = {**{s: "Tech" for s in tech}, **{s: "Energy" for s in energy}}
    monkeypatch.setattr(fl.universe, "get_sp500_constituents_asof", _fake_universe(symbols))
    monkeypatch.setattr(fl.screener_asof, "build_ranking_as_of", _fake_ranking(scores, sectors))

    result = fl.run_factor_analysis("2024-01-02", "2024-02-02", months=1, max_symbols=len(symbols),
                                    mode="fast_dev", factor_cols=("composite_score",),
                                    horizons_months=(1,), n_quantiles=2)
    summary = result["summary"]
    raw = summary[~summary["sector_neutral"]].iloc[0]
    neutral = summary[summary["sector_neutral"]].iloc[0]
    assert raw["ic_mean"] > 0.7  # capta el efecto sectorial -> IC alto
    assert raw["ic_mean"] > abs(neutral["ic_mean"]) + 0.4  # sector-neutral lo filtra en gran medida


def test_skips_period_with_insufficient_universe_coverage(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(fl, "_MIN_ROWS_PER_QUANTILE", 4)  # restaura el umbral real de produccion
    symbols = ["A", "B", "C"]  # solo 1/3 elegible -> por debajo de min_universe_coverage=0.5
    monkeypatch.setattr(fl.universe, "get_sp500_constituents_asof", _fake_universe(symbols))
    monkeypatch.setattr(fl.screener_asof, "build_ranking_as_of",
                        lambda day, symbols: {"table": pd.DataFrame(
                            {"composite_score": [80, None, None], "score_coverage": [.9, 0, 0],
                             "sector": ["Tech"] * 3}, index=symbols)})
    result = fl.run_factor_analysis("2024-01-02", "2024-02-02", months=1, max_symbols=len(symbols),
                                    mode="fast_dev")
    assert result["summary"].empty
    assert len(result["skipped"]) == 1
    assert "cobertura insuficiente" in result["skipped"][0]["motivo"]
