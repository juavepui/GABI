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
