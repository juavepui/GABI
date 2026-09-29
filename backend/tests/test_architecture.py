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
