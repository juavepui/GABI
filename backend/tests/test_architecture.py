import ast
import json
import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GUARD = runpy.run_path(str(ROOT / "scripts/check_architecture.py"))


@pytest.mark.parametrize(("module", "target"), [
    ("gabi.domain.market.scoring", "gabi.domain.market.metrics"),
    ("gabi.domain.portfolio.costs", "numpy"),
    ("gabi.application.market.ranking", "gabi.domain.market.scoring"),
    ("gabi.infrastructure.storage.market", "gabi.application.market.ports"),
    ("gabi.infrastructure.legacy.screener", "gabi.screener.build_screener_table"),
    ("gabi_api.routes.market", "gabi.application.market.ranking"),
    ("gabi_api.bootstrap", "gabi.infrastructure.storage.market"),
])
def test_dependencies_follow_the_allowed_direction(module, target):
    assert GUARD["dependency_error"](module, target) is None


@pytest.mark.parametrize(("module", "target"), [
    ("gabi.domain.market.scoring", "gabi.application.market.ranking"),
    ("gabi.application.market.ranking", "gabi.infrastructure.storage.market"),
    ("gabi.application.market.ranking", "gabi.scoring"),
    ("gabi.domain.market.scoring", "sqlite3"),
    ("gabi.application.market.ranking", "requests"),
    ("gabi.infrastructure.providers.sec", "streamlit"),
    ("gabi.infrastructure.legacy.screener", "gabi.evidence_ui.render"),
    ("gabi_api.routes.market", "gabi.storage"),
    ("gabi_api.routes.market", "gabi.infrastructure.storage.market"),
    ("gabi_api.routes.market", "gabi_cli.bootstrap"),
    ("gabi.infrastructure.storage.market", "app.pages.screener"),
    ("gabi.application.market.ranking", "<dynamic-import>"),
])
def test_wrong_layer_and_hidden_dependencies_are_rejected(module, target):
    assert GUARD["dependency_error"](module, target)


def test_parser_finds_relative_function_type_and_dynamic_imports():
    tree = ast.parse("""
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..infrastructure import storage
def run():
    from . import scoring
    importlib.import_module('gabi.storage')
    importlib.import_module(variable)
""")
    dependencies = {target for target, _ in GUARD["imports"](tree, "gabi.application.market")}
    assert {"gabi.infrastructure.storage", "gabi.application.scoring", "gabi.storage", "<dynamic-import>"} <= dependencies


def write(root, name, text):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_legacy_debt_cannot_expand_and_retired_exceptions_must_be_removed(tmp_path):
    write(tmp_path, ".github/architecture-legacy.json", json.dumps({"backend/src/gabi/old.py": ["gabi.storage"]}))
    write(tmp_path, "backend/src/gabi/old.py", "from . import storage\nfrom . import screener\n")
    assert any("new legacy dependency gabi.screener" in error for error in GUARD["check"](tmp_path))
    write(tmp_path, "backend/src/gabi/old.py", "")
    assert any("remove retired dependency gabi.storage" in error for error in GUARD["check"](tmp_path))
    write(tmp_path, "backend/src/gabi/new_flat_module.py", "")
    assert any("new flat/Streamlit module" in error for error in GUARD["check"](tmp_path))


def test_compatibility_facade_can_delegate_sql_and_http_only_to_concrete_adapters(tmp_path):
    write(tmp_path, ".github/architecture-legacy.json", json.dumps({"backend/src/gabi/old.py": []}))
    write(tmp_path, "backend/src/gabi/infrastructure/storage/sec_reads.py", "class Reader: pass\n")
    write(tmp_path, "backend/src/gabi/infrastructure/providers/sec.py", "class Source: pass\n")
    for allowed in ("from gabi.infrastructure.storage.sec_reads import Reader\n",
                    "from gabi.infrastructure.providers.sec import Source\n"):
        write(tmp_path, "backend/src/gabi/old.py", allowed)
        assert GUARD["check"](tmp_path) == []
    for target in ("providers", "legacy.sec", "settings", "storage"):
        write(tmp_path, "backend/src/gabi/old.py", f"import gabi.infrastructure.{target}\n")
        assert any("new legacy dependency" in error for error in GUARD["check"](tmp_path))
    for adapter, line in (("storage/sec_reads.py", "from gabi.infrastructure.storage.sec_reads import Reader\n"),
                          ("providers/sec.py", "from gabi.infrastructure.providers.sec import Source\n")):
        write(tmp_path, "backend/src/gabi/old.py", line)
        write(tmp_path, f"backend/src/gabi/infrastructure/{adapter}", "from gabi import old\n")
        errors = GUARD["check"](tmp_path)
        assert any("infrastructure cannot depend on legacy" in error for error in errors)
        assert any("dependency cycle" in error for error in errors)
        write(tmp_path, f"backend/src/gabi/infrastructure/{adapter}", "VALUE = 1\n")


def test_io_through_pandas_and_cycles_are_detected_without_executing_code(tmp_path):
    write(tmp_path, ".github/architecture-legacy.json", "{}")
    write(tmp_path, "backend/src/gabi/domain/market/a.py", "from . import b\npd.read_csv('never-opened.csv')\n")
    write(tmp_path, "backend/src/gabi/domain/market/b.py", "from . import a\n")
    errors = GUARD["check"](tmp_path)
    assert any("direct I/O read_csv" in error for error in errors)
    assert any("dependency cycle" in error for error in errors)
    assert not (tmp_path / "never-opened.csv").exists()


def test_mixed_cycle_is_not_hidden_by_preexisting_legacy_cycles():
    graph = {
        "gabi.a": {"gabi.b", "gabi.application.market"},
        "gabi.b": {"gabi.a"},
        "gabi.application.market": {"gabi.b"},
    }
    assert GUARD["dependency_cycles"](graph)
    assert not GUARD["dependency_cycles"]({"gabi.a": {"gabi.b"}, "gabi.b": {"gabi.a"}})


def test_current_repository_has_no_unregistered_architecture_debt():
    assert GUARD["check"](ROOT) == []


def test_editing_the_baseline_cannot_whitelist_new_debt():
    previous = {"old.py": ["gabi.storage"]}
    current = {"old.py": ["gabi.storage", "streamlit"], "new_flat.py": []}
    errors = GUARD["baseline_growth"](previous, current)
    assert any("cannot add module new_flat.py" in error for error in errors)
    assert any("cannot add dependency old.py -> streamlit" in error for error in errors)


def test_baseline_can_only_shrink_when_modules_or_dependencies_are_retired():
    previous = {"old.py": ["gabi.storage", "streamlit"], "retired.py": []}
    assert GUARD["baseline_growth"](previous, {"old.py": ["gabi.storage"]}) == []


def test_config_may_only_replace_a_retired_storage_dependency():
    previous = {"old.py": ["gabi.storage", "pandas"], "other.py": ["pandas"]}
    assert GUARD["baseline_growth"](previous, {"old.py": ["gabi.config", "pandas"], "other.py": ["pandas"]}) == []
    kept = GUARD["baseline_growth"](previous, {"old.py": ["gabi.config", "gabi.storage", "pandas"]})
    assert kept == ["legacy baseline cannot add dependency old.py -> gabi.config"]
    unrelated = GUARD["baseline_growth"](previous, {"other.py": ["gabi.config", "pandas"]})
    assert unrelated == ["legacy baseline cannot add dependency other.py -> gabi.config"]
    other = GUARD["baseline_growth"](previous, {"old.py": ["gabi.edgar", "pandas"]})
    assert other == ["legacy baseline cannot add dependency old.py -> gabi.edgar"]


def test_retired_streamlit_cannot_return_as_import_or_dependency(tmp_path):
    write(tmp_path, ".github/architecture-legacy.json", json.dumps({"backend/src/gabi/old.py": ["streamlit"]}))
    write(tmp_path, "backend/src/gabi/old.py", "import streamlit\n")
    write(tmp_path, "backend/pyproject.toml", '[project]\ndependencies = ["streamlit>=1"]\n')
    errors = GUARD["check"](tmp_path)
    assert any("Streamlit import was retired" in error for error in errors)
    assert any("Streamlit dependency was retired" in error for error in errors)


def compatibility_repo(root, permanent: dict, pending: dict, modules: dict) -> None:
    write(root, ".github/architecture-legacy.json", json.dumps({f"backend/src/gabi/{name}.py": deps
                                                               for name, (_, deps) in modules.items()}))
    for name, (source, _) in modules.items():
        write(root, f"backend/src/gabi/{name}.py", source)
    write(root, "backend/legacy-engine-hashes.json", json.dumps({"engine.py": "0" * 64}))
    write(root, ".github/architecture-compatibility.json", json.dumps({"permanent": permanent, "pending": pending}))


def test_every_flat_module_is_classified_and_frozen_engines_are_not_listed(tmp_path):
    keep = {"reason": "hashed by name", "consumers": ["engine"]}
    compatibility_repo(tmp_path, {"kept": keep, "engine": keep}, {"later": "#90", "gone": "#90"},
                       {"kept": ("", []), "later": ("", []), "engine": ("", []), "stray": ("", [])})
    errors = GUARD["check"](tmp_path)
    assert "backend/src/gabi/stray.py: unclassified flat module; list it as permanent or pending (ADR 0006)" in errors
    assert any("frozen engine engine is verified by hash" in error for error in errors)
    assert any("remove retired module gone" in error for error in errors)


def test_permanent_modules_cannot_gain_sql_http_or_processes(tmp_path):
    keep = {"reason": "hashed by name", "consumers": ["engine"]}
    modules = {"kept": ("import requests\nimport sqlite3\nfrom urllib import request\n", ["requests", "sqlite3", "urllib"]),
               "later": ("import subprocess\n", ["subprocess"])}
    compatibility_repo(tmp_path, {"kept": keep | {"io": ["sqlite3", "yfinance"]}}, {"later": "#90"}, modules)
    errors = GUARD["check"](tmp_path)
    assert "backend/src/gabi/kept.py: permanent compatibility module cannot use requests (ADR 0006)" in errors
    assert "backend/src/gabi/kept.py: permanent compatibility module cannot use urllib (ADR 0006)" in errors
    assert not any("cannot use sqlite3" in error for error in errors)  # justified exception
    assert any("remove unused I/O exception kept -> yfinance" in error for error in errors)
    assert not any("later.py" in error for error in errors)  # pending modules are debt, not permanent


def test_compatibility_inventory_only_shrinks():
    previous = {"permanent": {"kept": {"io": ["sqlite3"]}}, "pending": {"later": "#90", "retired": "#90"}}
    assert GUARD["compatibility_growth"](previous, {"permanent": {"kept": {}, "later": {}}, "pending": {}}) == []
    errors = GUARD["compatibility_growth"](previous, {"permanent": {"kept": {"io": ["sqlite3", "requests"]}, "new": {}},
                                                      "pending": {"later": "#90", "other": "#90"}})
    assert errors == [".github/architecture-compatibility.json: cannot add pending module other",
                      ".github/architecture-compatibility.json: cannot add permanent module new unless it was pending",
                      ".github/architecture-compatibility.json: cannot add I/O exception kept -> requests"]
    assert GUARD["compatibility_growth"](previous, None) == [
        ".github/architecture-compatibility.json: the compatibility inventory cannot be removed (ADR 0006)"]


def test_current_compatibility_inventory_is_closed():
    inventory = json.loads((ROOT / ".github/architecture-compatibility.json").read_text(encoding="utf-8"))
    frozen = {name.removesuffix(".py") for name in json.loads((ROOT / "backend/legacy-engine-hashes.json").read_text())}
    flat = {path.stem for path in (ROOT / "backend/src/gabi").glob("*.py")} - {"__init__"}
    assert set(inventory["permanent"]) | set(inventory["pending"]) | frozen == flat
    assert {name for name, entry in inventory["permanent"].items() if entry.get("io")} == {"smallmid_test", "storage"}
