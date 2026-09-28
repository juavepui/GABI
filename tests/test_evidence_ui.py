from streamlit.testing.v1 import AppTest

from gabi import evidence_confidence


def test_modes_show_candidate_reasons_and_keep_high_score_separate(monkeypatch):
    from test_evidence_confidence import NOW, frame

    frozen = frame()
    build = evidence_confidence.build
    monkeypatch.setattr(evidence_confidence, "build", lambda data, weights: build(frozen, weights, now=NOW))
    app = AppTest.from_string('''
import streamlit as st
import pandas as pd
from gabi import evidence_ui, scoring
mode = st.selectbox("Mode", ["INVESTOR", "RESEARCH"])
evidence_ui.render(pd.DataFrame(), scoring.DEFAULT_WEIGHTS, mode=mode)
''').run()
    assert not app.exception
    overview = app.dataframe[0].value
    assert len(overview) == 20
    assert overview.iloc[0]["Score"] == 99
    assert set(overview["Confianza de evidencia"]) == {"BAJA"}
    assert set(overview["Score con apoyo tras Holm"]) == {"0.0%"}
    assert any("no es probabilidad" in c.value for c in app.caption)
    assert any("Capacidad predictiva" in m.value for m in app.markdown)
    assert any("#44" in m.value for m in app.markdown)
    app.selectbox[1].set_value("F02").run()
    assert not app.exception and app.metric[0].value == "BAJA"
    app.selectbox[0].set_value("RESEARCH").run()
    assert not app.exception and len(app.json) == 1


def test_empty_data_and_company_specific_view():
    app = AppTest.from_string('''
import pandas as pd
from gabi import evidence_ui, scoring
evidence_ui.render(pd.DataFrame(), scoring.DEFAULT_WEIGHTS)
''').run()
    assert not app.exception and "no disponible" in app.info[0].value
