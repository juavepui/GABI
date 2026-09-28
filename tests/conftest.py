"""Aislamiento por defecto: ningún test escribe en la base de datos real.

Un test que olvidaba aislarse escribió precios ficticios en data/gabi.db (#43).
Cada test recibe una base y un directorio de datos temporales; los que ya se
aislaban siguen funcionando porque su monkeypatch se aplica después.
"""

import pytest

from gabi import config


@pytest.fixture(autouse=True)
def _default_isolated_data(tmp_path_factory, monkeypatch):
    root = tmp_path_factory.mktemp("gabi-data")
    monkeypatch.setattr(config, "DATA_DIR", root)
    monkeypatch.setattr(config, "DB_PATH", root / "gabi.db")


@pytest.fixture(autouse=True)
def _isolated_smallmid_paths(tmp_path_factory, monkeypatch):
    """smallmid_test fija sus carpetas al importarse; ningún test debe escribir en las reales (#44)."""
    from gabi import smallmid_test
    root = tmp_path_factory.mktemp("smallmid")
    monkeypatch.setattr(smallmid_test, "WORK", root / "work")
    monkeypatch.setattr(smallmid_test, "OUTPUT", root / "docs")
