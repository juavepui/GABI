"""Aislamiento por defecto: ningún test escribe en la base de datos real.

Un test que olvidaba aislarse escribió precios ficticios en data/gabi.db (#43).
Cada test recibe una base y un directorio de datos temporales; los que ya se
aislaban siguen funcionando porque su monkeypatch se aplica después.
"""

from pathlib import Path

import pytest

from gabi import config


@pytest.fixture(autouse=True)
def _default_isolated_data(tmp_path_factory, monkeypatch):
    root = tmp_path_factory.mktemp("gabi-data")
    previous_data = config.DATA_DIR
    # config keeps paths computed at import time. Changing DATA_DIR/DB_PATH
    # alone left save_weights and key/cache paths pointing at the real data.
    for name, value in list(vars(config).items()):
        if isinstance(value, Path) and value.is_relative_to(previous_data):
            monkeypatch.setattr(config, name, root / value.relative_to(previous_data))
    from gabi import app_mode

    monkeypatch.setattr(app_mode, "MODE_PATH", root / "app_mode.json")


@pytest.fixture(autouse=True)
def _isolated_smallmid_paths(tmp_path_factory, monkeypatch):
    """smallmid_test fija sus carpetas al importarse; ningún test debe escribir en las reales (#44)."""
    from gabi import smallmid_test
    root = tmp_path_factory.mktemp("smallmid")
    monkeypatch.setattr(smallmid_test, "WORK", root / "work")
    monkeypatch.setattr(smallmid_test, "OUTPUT", root / "docs")
