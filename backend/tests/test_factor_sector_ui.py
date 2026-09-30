import shutil
from pathlib import Path

from streamlit.testing.v1 import AppTest

from gabi import config, evidence_catalog, factor_sector_stability, factor_sector_ui
from gabi.infrastructure.storage.published_factors import FilePublishedFactors

SOURCE_ROOT = Path(__file__).resolve().parents[2]


def copied_publications(root):
    for path in FilePublishedFactors(SOURCE_ROOT)._paths():
        if path.is_relative_to(SOURCE_ROOT / "docs"):
            destination = root / path.relative_to(SOURCE_ROOT)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)


def test_saved_factor_map_exposes_insufficient_groups_without_reanalysis(tmp_path, monkeypatch):
    copied_publications(tmp_path)
    monkeypatch.setattr(config, "BASE_DIR", tmp_path)
    monkeypatch.setattr(factor_sector_stability, "OUTPUT", tmp_path / "docs" / "factor-zoo-sector")
    factor_sector_ui._source.clear()
    original_load = evidence_catalog.load
    calls = 0

    def counted_load():
        nonlocal calls
        calls += 1
        return original_load()

    monkeypatch.setattr(evidence_catalog, "load", counted_load)
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
    assert calls == 1  # Streamlit reruns stat files; it does not rehash them.
    csv = tmp_path / "docs/factor-zoo-sector/coverage.csv"
    csv.write_text(csv.read_text(encoding="utf-8") + "tampered\n", encoding="utf-8")
    app.run()
    assert calls == 2 and app.warning and not app.dataframe


def test_unverified_catalogue_hides_factor_map(monkeypatch):
    factor_sector_ui._source.clear()
    monkeypatch.setattr(evidence_catalog, "load", lambda: {"available": False, "errors": ["factor-zoo-sector: modificado"]})
    app = AppTest.from_string('''
from gabi import factor_sector_ui
factor_sector_ui.render()
''').run()
    assert not app.exception and app.warning
    assert not app.dataframe
