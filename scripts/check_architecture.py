"""Check source dependencies without importing GABI or touching application data."""

import argparse
import ast
import importlib.util
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAYERS = {"domain", "application", "infrastructure"}
PURE_LIBRARIES = {"numpy", "pandas", "scipy", "quantstats", "pypfopt", "backtesting", "exchange_calendars"}
IO_MODULES = {"os", "pathlib", "sqlite3", "subprocess", "socket", "http", "urllib", "shutil", "tempfile",
              "multiprocessing", "concurrent", "importlib", "builtins", "io", "sys"}
UI_MODULES = {"streamlit", "plotly", "fastapi", "starlette"}
# ADR 0006: permanent compatibility modules never gain SQL, HTTP or processes.
DIRECT_IO = {"sqlite3", "requests", "httpx", "urllib", "http", "socket", "subprocess", "yfinance", "lxml", "aiohttp"}
COMPATIBILITY = ".github/architecture-compatibility.json"
FROZEN_ENGINES = "backend/legacy-engine-hashes.json"
IO_CALLS = {"open", "read_csv", "read_json", "read_sql", "read_sql_query", "read_sql_table", "read_pickle",
            "to_csv", "to_json", "to_sql", "to_pickle", "read_text", "write_text", "read_bytes", "write_bytes",
            "mkdir", "unlink", "rmdir"}


def source_module(path: Path, source: Path) -> str:
    parts = list(path.relative_to(source).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def imports(tree: ast.AST, module: str, package: bool = False) -> list[tuple[str, int]]:
    """Include imports inside functions, TYPE_CHECKING, and literal dynamic imports."""
    result = []
    owner = module if package else module.rpartition(".")[0]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.extend((alias.name, node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                base = importlib.util.resolve_name("." * node.level + base, owner)
            if not node.module or base.split(".")[0] in {"gabi", "gabi_api", "gabi_cli"}:
                result.extend((base + "." + alias.name, node.lineno) for alias in node.names)
            else:
                result.append((base, node.lineno))
        elif isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
            if name in {"__import__", "import_module"}:
                target = node.args[0].value if node.args and isinstance(node.args[0], ast.Constant) else None
                if isinstance(target, str) and target.startswith("."):
                    target = importlib.util.resolve_name(target, owner)
                result.append((target if isinstance(target, str) else "<dynamic-import>", node.lineno))
    return result


def layer(module: str) -> str:
    parts = module.split(".")
    if parts[0] in {"gabi_api", "gabi_cli"}:
        return "bootstrap" if parts[-1] == "bootstrap" else "transport"
    if parts[0] == "gabi" and len(parts) > 1 and parts[1] in LAYERS:
        return parts[1]
    return "legacy"


def legacy_dependency(target: str) -> bool:
    top = target.split(".")[0]
    return top not in sys.stdlib_module_names or top in IO_MODULES or top in UI_MODULES


def dependency_error(module: str, target: str) -> str | None:
    own = layer(module)
    top = target.split(".")[0]
    if target == "<dynamic-import>":
        return "nonliteral dynamic import hides dependencies"
    if top in {"app", "frontend"}:
        return "backend cannot import frontend/Streamlit adapters"
    if top not in {"gabi", "gabi_api", "gabi_cli"}:
        if own in {"domain", "application"}:
            if top in IO_MODULES or (top not in sys.stdlib_module_names and top not in PURE_LIBRARIES):
                return "domain/application cannot depend on I/O or frameworks"
        elif own == "infrastructure" and top in UI_MODULES:
            return "infrastructure cannot depend on presentation frameworks"
        return None
    other = layer(target)
    allowed = {
        "domain": {"domain"},
        "application": {"domain", "application"},
        "infrastructure": {"domain", "application", "infrastructure"},
        "transport": {"domain", "application", "transport", "bootstrap"},
        "bootstrap": {"domain", "application", "infrastructure", "transport", "bootstrap"},
    }
    if own == "transport" and other in {"transport", "bootstrap"} and module.split(".")[0] != top:
        return "HTTP and CLI adapters do not import each other"
    if other == "legacy" and own == "infrastructure" and module.startswith("gabi.infrastructure.legacy."):
        name = target.split(".")[1] if target.startswith("gabi.") else target
        if name.endswith("_ui") or name == "ui_helpers":
            return "legacy bridge cannot import Streamlit helpers"
        return None
    if other not in allowed.get(own, set()):
        return f"{own} cannot depend on {other}; legacy access belongs in infrastructure/legacy"
    return None


def dependency_cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    """Report cycles that involve new layers; wholly legacy cycles remain debt."""
    stack: list[str] = []
    active: set[str] = set()
    indices: dict[str, int] = {}
    low: dict[str, int] = {}
    found = []

    def visit(node):
        indices[node] = low[node] = len(indices)
        stack.append(node)
        active.add(node)
        for dependency in sorted(graph[node]):
            if dependency not in indices:
                visit(dependency)
                low[node] = min(low[node], low[dependency])
            elif dependency in active:
                low[node] = min(low[node], indices[dependency])
        if low[node] == indices[node]:
            component = []
            while True:
                item = stack.pop()
                active.remove(item)
                component.append(item)
                if item == node:
                    break
            if len(component) > 1 and any(layer(item) != "legacy" for item in component):
                found.append(sorted(component))

    for node in sorted(graph):
        if node not in indices:
            visit(node)
    return found


def check(root: Path) -> list[str]:
    baseline = json.loads((root / ".github/architecture-legacy.json").read_text(encoding="utf-8"))
    source = root / "backend/src"
    files = sorted(source.rglob("*.py")) + sorted((root / "app").rglob("*.py"))
    modules = {source_module(path, source): path for path in files if path.is_relative_to(source)}
    graph: dict[str, set[str]] = {name: set() for name in modules}
    errors = []
    project_file = root / "backend/pyproject.toml"
    if project_file.exists():
        project = tomllib.loads(project_file.read_text(encoding="utf-8"))
        requirements = list(project.get("project", {}).get("dependencies", []))
        requirements.extend(requirement for group in project.get("dependency-groups", {}).values()
                            for requirement in group)
        requirements.extend(requirement for group in project.get("project", {}).get("optional-dependencies", {}).values()
                            for requirement in group)
        if any(re.split(r"[\s\[<>=!~;]", requirement, maxsplit=1)[0].lower().replace("_", "-") == "streamlit"
               for requirement in requirements):
            errors.append("backend/pyproject.toml: Streamlit dependency was retired; use React")
    current_legacy = set()
    legacy_imports: dict[str, set[str]] = {}
    for path in files:
        relative = path.relative_to(root).as_posix()
        module = source_module(path, source) if path.is_relative_to(source) else "app." + path.stem
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
        dependencies = imports(tree, module, path.name == "__init__.py")
        for target, line in dependencies:
            if target.split(".")[0] == "streamlit":
                errors.append(f"{relative}:{line}: Streamlit import was retired; use React")
        own = layer(module)
        if own == "legacy":
            current_legacy.add(relative)
            legacy_imports[relative] = {target.split(".")[0] for target, _ in dependencies}
            if relative not in baseline:
                errors.append(f"{relative}: new flat/Streamlit module; use the architecture directories")
                continue
            # ADR 0003/0004: replace compatibility SQL/HTTP with concrete storage/provider adapters.
            # Neither imports legacy; mixed cycles are still rejected.
            tracked = {target for target, _ in dependencies if legacy_dependency(target)
                       and layer(target) not in {"domain", "application"}
                       and not target.startswith(("gabi.infrastructure.storage.", "gabi.infrastructure.providers."))}
            expected = set(baseline[relative])
            for target in sorted(tracked - expected):
                errors.append(f"{relative}: new legacy dependency {target}; extract into the correct layer")
            for target in sorted(expected - tracked):
                errors.append(f"{relative}: remove retired dependency {target} from the legacy baseline")
        else:
            for target, line in dependencies:
                message = dependency_error(module, target)
                if message:
                    errors.append(f"{relative}:{line}: {target}: {message}")
            if own in {"domain", "application"}:
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call):
                        name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
                        if name in IO_CALLS:
                            errors.append(f"{relative}:{node.lineno}: direct I/O {name}; use an application port")
        if module in graph:
            for target, _ in dependencies:
                while target and target not in graph:
                    target = target.rpartition(".")[0]
                if target and target != module:
                    graph[module].add(target)
    for retired in sorted(set(baseline) - current_legacy):
        errors.append(f"{retired}: remove retired module from the legacy baseline")
    errors.extend(compatibility_errors(root, legacy_imports))
    errors.extend("dependency cycle component: " + ", ".join(cycle) for cycle in dependency_cycles(graph))
    return errors


def compatibility_errors(root: Path, legacy_imports: dict[str, set[str]]) -> list[str]:
    """ADR 0006: every non-frozen flat module is classified; permanent ones have no direct SQL/HTTP/process I/O."""
    path = root / COMPATIBILITY
    if not path.exists():
        return []  # Removing the inventory is rejected by compare_baseline against the base ref.
    inventory = json.loads(path.read_text(encoding="utf-8"))
    permanent, pending = inventory.get("permanent", {}), inventory.get("pending", {})
    frozen_file = root / FROZEN_ENGINES
    frozen = {name.removesuffix(".py") for name in json.loads(frozen_file.read_text(encoding="utf-8"))}         if frozen_file.exists() else set()
    flat = {Path(relative).stem: imported for relative, imported in legacy_imports.items()
            if relative.startswith("backend/src/gabi/") and relative.count("/") == 3 and not relative.endswith("__init__.py")}
    errors = [f"{COMPATIBILITY}: {name} is both permanent and pending" for name in sorted(set(permanent) & set(pending))]
    errors.extend(f"{COMPATIBILITY}: frozen engine {name} is verified by hash, not listed"
                  for name in sorted((set(permanent) | set(pending)) & frozen))
    errors.extend(f"{COMPATIBILITY}: remove retired module {name}"
                  for name in sorted((set(permanent) | set(pending)) - set(flat)))
    for name in sorted(set(flat) - frozen - set(permanent) - set(pending)):
        errors.append(f"backend/src/gabi/{name}.py: unclassified flat module; list it as permanent or pending (ADR 0006)")
    for name, entry in sorted(permanent.items()):
        if not entry.get("reason") or not entry.get("consumers"):
            errors.append(f"{COMPATIBILITY}: permanent {name} needs a reason and its consumers")
        if name not in flat:
            continue
        allowed = set(entry.get("io", []))
        used = flat[name] & DIRECT_IO
        errors.extend(f"backend/src/gabi/{name}.py: permanent compatibility module cannot use {target} (ADR 0006)"
                      for target in sorted(used - allowed))
        errors.extend(f"{COMPATIBILITY}: remove unused I/O exception {name} -> {target}"
                      for target in sorted(allowed - used))
    errors.extend(f"{COMPATIBILITY}: pending {name} needs the issue that retires or justifies it"
                  for name, note in sorted(pending.items()) if not note)
    return errors


def compatibility_growth(previous: dict, current: dict | None) -> list[str]:
    """The pending list and the I/O exceptions only shrink; a module is promoted only from pending."""
    if current is None:
        return [f"{COMPATIBILITY}: the compatibility inventory cannot be removed (ADR 0006)"]
    before = set(previous.get("permanent", {})) | set(previous.get("pending", {}))
    errors = [f"{COMPATIBILITY}: cannot add pending module {name}"
              for name in sorted(set(current.get("pending", {})) - set(previous.get("pending", {})))]
    errors.extend(f"{COMPATIBILITY}: cannot add permanent module {name} unless it was pending"
                  for name in sorted(set(current.get("permanent", {})) - before))
    for name, entry in sorted(current.get("permanent", {}).items()):
        old = previous.get("permanent", {}).get(name)
        granted = set(entry.get("io", [])) - (set(old.get("io", [])) if old else set())
        errors.extend(f"{COMPATIBILITY}: cannot add I/O exception {name} -> {target}" for target in sorted(granted))
    return errors


def baseline_growth(previous: dict, current: dict) -> list[str]:
    errors = [f"legacy baseline cannot add module {name}" for name in sorted(set(current) - set(previous))]
    for name in sorted(set(previous) & set(current)):
        added = set(current[name]) - set(previous[name])
        # ADR 0005: gabi.config may only replace a retired gabi.storage used to resolve the database path.
        if "gabi.config" in added and "gabi.storage" in previous[name] and "gabi.storage" not in current[name]:
            added.discard("gabi.config")
        errors.extend(f"legacy baseline cannot add dependency {name} -> {target}" for target in sorted(added))
    return errors


def compare_baseline(root: Path, reference: str) -> list[str]:
    name = ".github/architecture-legacy.json"
    listing = subprocess.run(["git", "ls-tree", reference, "--", name], cwd=root,
                             capture_output=True, text=True, check=True)
    if not listing.stdout.strip():
        # First introduction of the inventory; an absent/invalid ref still fails.
        return []
    previous = subprocess.run(["git", "show", f"{reference}:{name}"], cwd=root,
                              capture_output=True, text=True, encoding="utf-8", check=True)
    errors = baseline_growth(json.loads(previous.stdout), json.loads((root / name).read_text(encoding="utf-8")))
    listing = subprocess.run(["git", "ls-tree", reference, "--", COMPATIBILITY], cwd=root,
                             capture_output=True, text=True, check=True)
    if listing.stdout.strip():
        before = subprocess.run(["git", "show", f"{reference}:{COMPATIBILITY}"], cwd=root,
                                capture_output=True, text=True, encoding="utf-8", check=True)
        path = root / COMPATIBILITY
        errors.extend(compatibility_growth(json.loads(before.stdout),
                                           json.loads(path.read_text(encoding="utf-8")) if path.exists() else None))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--baseline-base", help="Git ref whose legacy exceptions must not grow (CI: HEAD^)")
    args = parser.parse_args()
    try:
        errors = check(args.root.resolve())
        if args.baseline_base:
            errors.extend(compare_baseline(args.root.resolve(), args.baseline_base))
    except (OSError, ValueError, SyntaxError, ImportError, subprocess.CalledProcessError) as exc:
        print(f"Architecture check failed: {exc}", file=sys.stderr)
        return 1
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("Backend architecture OK; legacy exceptions are explicit and cannot grow silently.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
