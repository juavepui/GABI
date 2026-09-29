import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from gabi import config, full_universe_audit, overfitting_audit, workspace


def test_legacy_aliases_read_physical_files_without_copies():
    root = workspace.RepositoryPath(workspace.ROOT)
    assert root / "src" / "gabi" / "config.py" == workspace.BACKEND / "src/gabi/config.py"
    assert root.joinpath("src", "gabi", "config.py") == root / "src/gabi/config.py"
    assert root / "uv.lock" == workspace.BACKEND / "uv.lock"
    assert root / "docs/search-ledger/ledger.json" == workspace.ROOT / "docs/search-ledger/ledger.json"
    assert (root / "src/gabi/config.py").is_file()
    assert not (workspace.ROOT / "src").exists()


@pytest.mark.parametrize("module", [overfitting_audit, full_universe_audit])
def test_cache_builder_source_names_keep_historical_manifest_keys(module):
    path = module.Path(module.__file__).with_name("config.py")
    assert path.is_file()
    assert path.relative_to(config.BASE_DIR).as_posix() == "src/gabi/config.py"
    # Other modules and the standard library are not patched.
    assert Path is not workspace.RepositoryPath


def test_published_cache_can_be_reused_without_rebuilding_rankings(tmp_path, monkeypatch):
    import pandas as pd

    monkeypatch.setattr(workspace, "DATA", tmp_path / "data")
    monkeypatch.setattr(config, "DATA_DIR", workspace.RepositoryPath(workspace.DATA))
    folder = tmp_path / "cache"
    folder.mkdir()
    (folder / "snapshot.db").write_bytes(b"test snapshot, no database opened")
    names = ("multifactor_backtest.py", "screener_asof.py", "scoring.py", "identity.py",
             "entity_master.py", "edgar.py", "technicals.py", "risk.py", "storage.py", "config.py", "universe.py")
    hashes = {"src/gabi/" + name: "pinned:" + name for name in names}
    hashes.update({"data/" + name: "pinned:" + name for name in
                   ("sp500_historical_membership.csv", "sec_cik_map.csv")})
    manifest = {"max_symbols": 200, "sources_sha256": hashes, "snapshot_sha256": "pinned:snapshot.db", "rankings": {}}
    for i in range(36):
        date = str((pd.Timestamp("2016-07-02") + pd.DateOffset(months=3 * i)).date())
        name = "ranking-" + date + ".csv"
        (folder / name).write_text("cached", encoding="utf-8")
        manifest["rankings"][date] = {"sha256": "pinned:" + name, "symbols": []}
    (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(overfitting_audit, "sha256", lambda path: "pinned:" + path.name)

    def forbidden(*args, **kwargs):
        raise AssertionError("A complete archived cache must not rebuild or open a database")

    monkeypatch.setattr(overfitting_audit.sqlite3, "connect", forbidden)
    monkeypatch.setattr(overfitting_audit.screener_asof, "build_ranking_as_of", forbidden)
    assert overfitting_audit.prepare_rankings(folder, progress=lambda *args, **kwargs: None) == manifest


@pytest.mark.parametrize("directory", ["root", "backend", "unrelated"])
def test_installed_backend_roots_are_independent_of_cwd(tmp_path, directory):
    cwd = {"root": workspace.ROOT, "backend": workspace.BACKEND, "unrelated": tmp_path}[directory]
    data = tmp_path / "isolated-data"
    env = {**os.environ, "GABI_DATA_DIR": str(data)}
    env.pop("PYTHONPATH", None)
    result = subprocess.run([sys.executable, "-c", "from gabi import config; from pathlib import Path; "
                             "import json; print(json.dumps({k:str(v) for k,v in vars(config).items() "
                             "if isinstance(v,Path)}))"], cwd=cwd, env=env, capture_output=True, text=True, check=True)
    paths = json.loads(result.stdout)
    assert Path(paths.pop("BASE_DIR")) == workspace.ROOT
    assert Path(paths["DATA_DIR"]) == data
    assert Path(paths["DB_PATH"]) == data / "gabi.db"
    assert all(Path(value).is_relative_to(data) for value in paths.values())
    assert not data.exists()  # Import does not initialize databases or create folders.


def test_relative_data_override_is_rejected_before_io(tmp_path):
    result = subprocess.run([sys.executable, "-c", "import gabi"], cwd=tmp_path,
                            env={**os.environ, "GABI_DATA_DIR": "data"}, capture_output=True, text=True)
    assert result.returncode != 0
    assert "GABI_DATA_DIR must be an absolute path" in result.stderr
    assert not (tmp_path / "data").exists()


def test_mypy_relocation_only_normalizes_backend_package_paths():
    from gabi import frozen_research_ci as ci

    record = ci.load_baseline()[0]
    for prefix in ("backend/", ci.BACKEND.as_posix() + "/"):
        assert ci.diagnostic_differences([{**record, "file": prefix + record["file"]}], [record]) == ({}, {})
    added, removed = ci.diagnostic_differences([{**record, "file": "other/" + record["file"]}], [record])
    assert sum(added.values()) == sum(removed.values()) == 1


def test_all_published_engines_and_original_config_remain_byte_identical():
    from gabi import frozen_research_ci as ci

    ci.verify_relocated_engines()


def test_periodic_cli_works_with_an_isolated_database_from_backend(tmp_path):
    (tmp_path / "sp500_constituents.csv").write_text("symbol,name,sector\nTEST,Test,Industrials\n", encoding="utf-8")
    setup = "from gabi import storage; storage.init_db(); from gabi.periodic_tasks import main; main()"
    result = subprocess.run([sys.executable, "-c", setup, "--status"],
                            cwd=workspace.BACKEND, env={**os.environ, "GABI_DATA_DIR": str(tmp_path), "PYTHONUTF8": "1"},
                            capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    assert isinstance(json.loads(result.stdout), dict)


def test_streamlit_home_runs_after_relocation_with_isolated_state(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest

    from gabi import app_mode

    monkeypatch.setattr(app_mode, "MODE_PATH", tmp_path / "app_mode.json")
    app = AppTest.from_file(str(workspace.ROOT / "app/streamlit_app.py"), default_timeout=20).run()
    assert not app.exception
    assert "GABI" in app.title[0].value
    assert any("Todavía no hay una estrategia demostrada" in box.value for box in app.info)


@pytest.mark.parametrize("page", sorted((workspace.ROOT / "app/pages").glob("*.py")), ids=lambda path: path.stem)
def test_all_transition_pages_start_with_isolated_empty_cache(page, monkeypatch):
    import socket

    import pandas as pd
    from streamlit.testing.v1 import AppTest

    from gabi import screener, screener_asof, storage, universe

    connect = socket.socket.connect

    def connect_local_only(sock, address):
        # Windows asyncio creates its internal socketpair over loopback.
        if isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1", "localhost"}:
            return connect(sock, address)
        pytest.fail("Startup smoke tests must not access the network")

    monkeypatch.setattr(socket.socket, "connect", connect_local_only)
    storage.init_db()
    empty = pd.DataFrame(columns=["symbol", "name", "sector", "industry"])
    monkeypatch.setattr(screener, "get_universe", lambda *args, **kwargs: empty)
    monkeypatch.setattr(screener, "build_screener_table", lambda *args, **kwargs: pd.DataFrame())
    info = {"symbols": [], "is_exact": False, "note": "Isolated startup smoke test"}
    monkeypatch.setattr(universe, "get_sp500_constituents_asof", lambda *args, **kwargs: info)
    monkeypatch.setattr(screener_asof, "build_ranking_as_of", lambda *args, **kwargs: {
        "table": pd.DataFrame(), "universe_info": info,
    })
    app = AppTest.from_file(str(page), default_timeout=30).run()
    assert not app.exception
    assert app.title


def test_default_fixture_isolates_weights_keys_and_cache_together():
    for name in ("DB_PATH", "WEIGHTS_PATH", "SP500_CACHE", "FRED_KEY_PATH", "TIINGO_KEY_PATH",
                 "NASDAQ_DATA_LINK_KEY_PATH", "FMP_KEY_PATH"):
        assert getattr(config, name).is_relative_to(config.DATA_DIR), name
        assert not getattr(config, name).is_relative_to(workspace.DATA), name
    config.save_weights({"value": 1.0, "quality": 0.0, "momentum": 0.0, "risk": 0.0})
    assert config.WEIGHTS_PATH.is_file()


def test_package_outside_checkout_resolves_runtime_sources_with_explicit_root(tmp_path):
    target = tmp_path / "installed"
    shutil.copytree(workspace.CODE, target / "gabi", ignore=shutil.ignore_patterns("__pycache__"))
    env = {**os.environ, "PYTHONPATH": str(target), "GABI_PROJECT_ROOT": str(workspace.ROOT),
           "GABI_DATA_DIR": str(tmp_path / "data")}
    script = "from gabi import config,overfitting_audit as oa; import json; " \
             "print(json.dumps([str(config.BASE_DIR),str(config.BASE_DIR/'src/gabi/config.py')," \
             "oa.Path(oa.__file__).relative_to(config.BASE_DIR).as_posix()]))"
    result = subprocess.run([sys.executable, "-c", script], cwd=tmp_path, env=env,
                            capture_output=True, text=True, check=True)
    root, source, logical = json.loads(result.stdout)
    assert Path(root) == workspace.ROOT
    assert Path(source) == target / "gabi/config.py"
    assert logical == "src/gabi/overfitting_audit.py"
