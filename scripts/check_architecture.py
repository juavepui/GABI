"""Check source dependencies without importing GABI or touching application data."""

import argparse
import ast
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAYERS = {"domain", "application", "infrastructure"}
PURE_LIBRARIES = {"numpy", "pandas", "scipy", "quantstats", "pypfopt", "backtesting", "exchange_calendars"}
IO_MODULES = {"os", "pathlib", "sqlite3", "subprocess", "socket", "http", "urllib", "shutil", "tempfile",
              "multiprocessing", "concurrent", "importlib", "builtins", "io", "sys"}
UI_MODULES = {"streamlit", "plotly", "fastapi", "starlette"}
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
    current_legacy = set()
    for path in files:
        relative = path.relative_to(root).as_posix()
        module = source_module(path, source) if path.is_relative_to(source) else "app." + path.stem
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
        dependencies = imports(tree, module, path.name == "__init__.py")
        own = layer(module)
        if own == "legacy":
            current_legacy.add(relative)
            if relative not in baseline:
                errors.append(f"{relative}: new flat/Streamlit module; use the architecture directories")
                continue
            tracked = {target for target, _ in dependencies if legacy_dependency(target)
                       and layer(target) not in {"domain", "application"}}
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
    errors.extend("dependency cycle component: " + ", ".join(cycle) for cycle in dependency_cycles(graph))
    return errors


def baseline_growth(previous: dict, current: dict) -> list[str]:
    errors = [f"legacy baseline cannot add module {name}" for name in sorted(set(current) - set(previous))]
    for name in sorted(set(previous) & set(current)):
        errors.extend(f"legacy baseline cannot add dependency {name} -> {target}"
                      for target in sorted(set(current[name]) - set(previous[name])))
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
    return baseline_growth(json.loads(previous.stdout), json.loads((root / name).read_text(encoding="utf-8")))


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
    print("Backend/Streamlit architecture OK; legacy exceptions are explicit and cannot grow silently.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
