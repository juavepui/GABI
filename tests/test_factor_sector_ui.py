from streamlit.testing.v1 import AppTest

from gabi import evidence_catalog, factor_sector_stability


def test_saved_factor_map_exposes_insufficient_groups_without_reanalysis(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("La UI no puede recalcular estudios ni leer la base operativa")

    monkeypatch.setattr(factor_sector_stability, "analyze", forbidden)
    monkeypatch.setattr(factor_sector_stability, "archived_filings", forbidden)
    app = AppTest.from_string('''
from gabi import factor_sector_ui
factor_sector_ui.render()
''').run()
    assert not app.exception
    assert len(app.dataframe[0].value) == 13
    assert len(app.dataframe[1].value) == 10
    assert "Insuficiente" in set(app.dataframe[1].value["Soporte temporal"])
    assert any("Holm" in caption.value for caption in app.caption)
    assert any("GICS" in caption.value for caption in app.caption)
    assert len(app.selectbox) == 1
    app.selectbox[0].set_value("momentum_12m").run()
    assert not app.exception and len(app.dataframe[1].value) == 10


def test_unverified_catalogue_hides_factor_map(monkeypatch):
    monkeypatch.setattr(evidence_catalog, "load", lambda: {"available": False, "errors": ["factor-zoo-sector: modificado"]})
    app = AppTest.from_string('''
from gabi import factor_sector_ui
factor_sector_ui.render()
''').run()
    assert not app.exception and app.warning
    assert not app.dataframe
