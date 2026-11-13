import numpy as np
import pandas as pd
import pytest

from gabi import smallmid_test as sm


def _quarter(rng, n=400, tail=0.0):
    score = rng.permutation(n).astype(float)
    returns = rng.normal(0.02, 0.10, n)
    returns[score >= n * 0.95] += tail  # solo el 5 % superior tiene señal
    return pd.DataFrame({"composite_score": score, "retorno": returns})


def _panels(rng, tail, quarters=57):
    rows = []
    for number in range(quarters):
        day = (pd.Timestamp("2011-07-02") + pd.DateOffset(months=3 * number)).date().isoformat()
        rows.append({"fecha": day, **sm.quarter_stats(_quarter(rng, tail=tail))})
    panel = pd.DataFrame(rows)
    return {"adversa": panel, "favorable": panel, "casos_completos": panel}


def test_adverse_bound_punishes_high_scores_without_returns():
    frame = pd.DataFrame({"composite_score": [1, 2, 3, 4, 5, 6], "retorno": [0.0, 0.1, 0.2, 0.3, None, None]})
    adverse = sm.apply_bound(frame, "adversa").retorno
    favourable = sm.apply_bound(frame, "favorable").retorno
    low, high = pd.Series([0.0, 0.1, 0.2, 0.3]).quantile([0.1, 0.9])
    assert adverse.iloc[4] == pytest.approx(low) and favourable.iloc[4] == pytest.approx(high)
    assert len(sm.apply_bound(frame, "casos_completos")) == 4


def test_quarter_stats_top_excess():
    frame = pd.DataFrame({"composite_score": range(100), "retorno": [0.0] * 80 + [0.10] * 20})
    row = sm.quarter_stats(frame)
    assert row["t1_top20"] == pytest.approx(0.10 - 0.02)
    assert row["t2_top5pct"] == pytest.approx(0.10 - 0.02)
    assert row["banda_80%-100%"] == pytest.approx(-0.02)


def test_planted_tail_signal_is_detected_and_noise_is_not():
    rng = np.random.default_rng(7)
    assert sm.analyze_panels(_panels(rng, tail=0.06))["decision_a1"] == "cola_robusta"
    assert sm.analyze_panels(_panels(rng, tail=0.0))["decision_a1"] in {"cola_no_concluyente", "sin_efecto_de_cola"}


def test_decisions_follow_the_preregistered_table():
    def stat(media, p):
        return {"media": media, "p_unilateral": p, "p_holm": p}
    both = {"t1_top20": stat(0.01, 0.01), "t2_top5pct": stat(0.01, 0.2)}
    weak = {"t1_top20": stat(0.01, 0.2), "t2_top5pct": stat(0.01, 0.3)}
    assert sm.decide_tail({"casos_completos": both, "adversa": both}) == "cola_robusta"
    assert sm.decide_tail({"casos_completos": both, "adversa": weak}) == "cola_condicionada_a_los_datos"
    assert sm.decide_tail({"casos_completos": weak, "adversa": weak}) == "cola_no_concluyente"
    negative = {"t1_top20": stat(-0.01, 0.9), "t2_top5pct": stat(0.01, 0.3)}
    assert sm.decide_tail({"casos_completos": negative, "adversa": negative}) == "sin_efecto_de_cola"
    assert sm.decide_primary({"casos_completos": stat(0.02, 0.01), "adversa": stat(0.01, 0.2)}) == \
        "condicionada_a_los_datos"
    assert sm.decide_primary({"casos_completos": stat(-0.01, 0.9), "adversa": stat(0.0, 0.5)}) == \
        "sin_capacidad_predictiva"


def test_holm_adjustment():
    assert sm.holm({"a": 0.01, "b": 0.04}) == {"a": 0.02, "b": 0.04}
    assert sm.holm({"a": 0.03, "b": 0.02}) == {"b": 0.04, "a": 0.04}


def test_forward_return_uses_last_price_when_the_series_ends_early():
    days = pd.bdate_range("2017-06-01", "2017-08-15")
    frame = pd.DataFrame({"adj_close": np.linspace(10, 12, len(days))}, index=days)
    value, ends = sm.forward_return(frame, "2017-07-02")
    entry = frame.adj_close[frame.index >= "2017-07-03"].iloc[0]
    assert ends and value == pytest.approx(12 / entry - 1)
    full = pd.DataFrame({"adj_close": 10.0}, index=pd.bdate_range("2017-06-01", "2017-12-31"))
    assert sm.forward_return(full, "2017-07-02") == (0.0, False)
    assert sm.forward_return(full[full.index < "2017-06-30"], "2017-07-02") == (None, True)


def test_addendum_refuses_once_rankings_exist(monkeypatch, tmp_path):
    monkeypatch.setattr(sm, "OUTPUT", tmp_path / "docs")
    monkeypatch.setattr(sm, "WORK", tmp_path / "work")
    (tmp_path / "work" / "rankings").mkdir(parents=True)
    (tmp_path / "work" / "rankings" / "ranking-2011-07-02.csv").write_text("x")
    with pytest.raises(ValueError, match="previa a los datos"):
        sm.preregister_addendum()


def test_addendum_registers_before_rankings_and_is_frozen(monkeypatch, tmp_path):
    monkeypatch.setattr(sm, "OUTPUT", tmp_path / "docs")
    monkeypatch.setattr(sm, "WORK", tmp_path / "work")
    (tmp_path / "docs").mkdir()
    monkeypatch.setattr(sm, "preregister", lambda: {"sha256": "base"})
    monkeypatch.setattr(sm.research_lab, "log_experiment", lambda *a, **k: 99)
    record = sm.preregister_addendum()
    assert record["sha256"] == sm.addendum_hash() and record["amends_sha256"] == "base"
    assert sm.preregister_addendum() == record
    monkeypatch.setitem(sm.ADDENDUM_A1, "hypothesis", "otra")
    with pytest.raises(ValueError, match="cambió"):
        sm.preregister_addendum()


def test_analysis_waits_for_all_rankings(monkeypatch, tmp_path):
    monkeypatch.setattr(sm, "WORK", tmp_path)
    monkeypatch.setattr(sm, "preregister", lambda: {"sha256": "base"})
    monkeypatch.setattr(sm, "preregister_addendum", lambda: {"sha256": "a1"})
    monkeypatch.setattr(sm, "_require_frozen", lambda: None)
    with pytest.raises(ValueError, match="Faltan 57 rankings"):
        sm.analyze()


def test_kaggle_cleaning_drops_one_day_reverting_spikes_only():
    prices = [10, 10, 30, 10, 10, 4, 4, 4]  # pico que se deshace (día 2) y caída real que se mantiene (día 5)
    frame = pd.DataFrame({"symbol": "X", "date": [f"2019-01-{d:02d}" for d in range(1, 9)],
                          "close_adjusted": prices})
    assert sm.clean_kaggle(frame).close_adjusted.tolist() == [10, 10, 10, 10, 4, 4, 4]


def test_series_agreement():
    days = pd.bdate_range("2019-01-01", periods=100)
    base = pd.DataFrame({"close": np.linspace(10, 20, 100), "adj_close": np.linspace(9, 18, 100)}, index=days)
    assert sm.series_agree(base, base.copy())["coincide"]
    other = base.assign(close=base.close * 3)  # otra empresa con el mismo ticker
    assert not sm.series_agree(base, other)["coincide"]
    assert sm.series_agree(base.iloc[:30], base.iloc[:30]) is None


def test_kaggle_is_last_priority_and_stops_at_the_cutoff(monkeypatch):
    checks = pd.DataFrame([{"cik": "1", "fuente": "kaggle", "simbolo": "OLD", "desde": "2009-01-02",
                            "hasta": "2021-06-01", "float_date": d, "outcome": "passed"}
                           for d in ("2016-06-30", "2017-06-30", "2018-06-30", "2019-06-30", "2020-06-30",
                                     "2021-01-01")])
    monkeypatch.setattr(sm, "kaggle_accepted", lambda: True)
    assert sm.usable(checks, "1", "2020-10-02") == ("kaggle", "OLD")
    assert sm.usable(checks, "1", "2021-04-02") is None  # el trimestre siguiente pasaría del corte
    yahoo = checks.assign(fuente="yahoo", simbolo="NEW")
    assert sm.usable(pd.concat([checks, yahoo]), "1", "2020-10-02") == ("yahoo", "NEW")
    monkeypatch.setattr(sm, "kaggle_accepted", lambda: False)
    assert sm.usable(checks, "1", "2020-10-02") is None


def test_addendum_a2_refuses_once_rankings_exist(monkeypatch, tmp_path):
    monkeypatch.setattr(sm, "OUTPUT", tmp_path / "docs")
    monkeypatch.setattr(sm, "WORK", tmp_path / "work")
    (tmp_path / "work" / "rankings").mkdir(parents=True)
    (tmp_path / "work" / "rankings" / "ranking-2011-07-02.csv").write_text("x")
    with pytest.raises(ValueError, match="previa a los datos"):
        sm.preregister_addendum_a2()


def test_data_freeze_by_complete_tiingo_run_or_deadline(monkeypatch, tmp_path):
    from datetime import date
    monkeypatch.setattr(sm, "WORK", tmp_path)
    assert not sm.data_frozen(date(2026, 10, 1))
    assert sm.data_frozen(date(2027, 1, 15))
    sm.mark_tiingo_complete({"fetched": 3, "stopped_at": "X"})  # detenida por el cupo: no cuenta
    assert not sm.data_frozen(date(2026, 10, 1))
    sm.mark_tiingo_complete({"fetched": 3, "cached": 800, "failed": 2})
    assert sm.data_frozen(date(2026, 10, 1))


def test_rankings_and_analysis_refuse_before_the_freeze(monkeypatch, tmp_path):
    monkeypatch.setattr(sm, "WORK", tmp_path)
    monkeypatch.setattr(sm, "preregister_addendum_a3", lambda: {"sha256": "a3"})
    monkeypatch.setattr(sm, "data_frozen", lambda today=None: False)
    with pytest.raises(ValueError, match="sin congelar"):
        sm.rankings()
    with pytest.raises(ValueError, match="sin congelar"):
        sm.analyze()
