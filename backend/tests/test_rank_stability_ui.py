from streamlit.testing.v1 import AppTest

from gabi import config, rank_stability_ui
from gabi import rank_stability as rs


def test_investor_and_research_show_different_details():
    code = '''
import numpy as np
import pandas as pd
from gabi import rank_stability_ui, scoring
scores = np.linspace(100, 1, 60)
frame = pd.DataFrame({**{f"{b}_score": scores for b in scoring.DEFAULT_WEIGHTS},
                      "composite_score": scores, "score_coverage": 1}, index=[f"F{i}" for i in range(60)])
mode = st.selectbox("Mode", ["INVESTOR", "RESEARCH"])
rank_stability_ui.render(frame, scoring.DEFAULT_WEIGHTS, mode=mode)
'''
    app = AppTest.from_string("import streamlit as st\n" + code).run()
    assert not app.exception
    assert len(app.dataframe) == 1
    assert len(app.dataframe[0].value) == 20
    assert app.metric[0].value == "100.0%"
    assert any("no es probabilidad" in c.value for c in app.caption)
    app.selectbox[0].set_value("RESEARCH").run()
    assert not app.exception
    assert len(app.dataframe) == 3
    assert len(app.dataframe[0].value) == 60
    assert len(app.dataframe[1].value) == 24


def test_invalid_data_produces_an_unavailable_message():
    app = AppTest.from_string('''
import pandas as pd
from gabi import rank_stability_ui, scoring
rank_stability_ui.render(pd.DataFrame(), scoring.DEFAULT_WEIGHTS, mode="INVESTOR")
''').run()
    assert not app.exception
    assert "no disponible" in app.info[0].value


def test_real_screener_reports_eligibility_before_search_filters(monkeypatch):
    from pathlib import Path

    from test_rank_stability import stable_panel

    from gabi import app_mode, evaluation, screener

    frame = stable_panel().assign(name="Firm", price=10., pe=10.)
    monkeypatch.setattr(app_mode, "get_mode", lambda: "INVESTOR")
    monkeypatch.setattr(config, "load_weights", lambda: dict(rs.scoring.DEFAULT_WEIGHTS))
    monkeypatch.setattr(screener, "get_universe", lambda **kwargs: frame)
    monkeypatch.setattr(screener, "build_screener_table", lambda *args, **kwargs: frame)
    monkeypatch.setattr(evaluation, "list_snapshots", lambda: frame.iloc[:0])
    captured = []
    original = rank_stability_ui.render

    def record(data, weights, *, mode):
        captured.append((len(data), mode))
        original(data, weights, mode=mode)

    monkeypatch.setattr(rank_stability_ui, "render", record)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[2] / "app/pages/1_Screener.py")).run()
    assert not app.exception
    app.sidebar.text_input[0].set_value("F000").run()
    assert not app.exception
    assert captured[-1] == (60, "INVESTOR")
    assert any("1 empresas" in c.value for c in app.caption)
