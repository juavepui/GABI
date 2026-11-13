"""Filesystem adapter for unchanged, published research engines.

RepositoryPath reads legacy src/gabi and uv.lock names at their new locations.
Its relative names preserve historical manifest keys. Only the two archived
cache builders need the same Path implementation for paths made from __file__;
their scoped loader leaves source bytes and financial calculations unchanged.
"""

import os
import sys
from importlib.abc import MetaPathFinder
from importlib.machinery import PathFinder, SourceFileLoader
from pathlib import Path
from types import ModuleType


def absolute_setting(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    path = Path(value).expanduser() if value else default
    if not path.is_absolute():
        raise ValueError(f"{name} must be an absolute path (independent of working directory).")
    return path.resolve()


def project_root() -> Path:
    explicit = os.environ.get("GABI_PROJECT_ROOT")
    if explicit:
        return absolute_setting("GABI_PROJECT_ROOT", Path(__file__).resolve().parents[3])
    for parent in Path(__file__).resolve().parents:
        if (parent / "backend" / "pyproject.toml").is_file() and (parent / "docs").is_dir():
            return parent
    raise RuntimeError("Cannot locate GABI repository; set absolute GABI_PROJECT_ROOT for a wheel installation.")


ROOT = project_root()
BACKEND = ROOT / "backend"
CODE = Path(__file__).resolve().parent
DATA = absolute_setting("GABI_DATA_DIR", ROOT / "data")


class RepositoryPath(Path):
    """Physical IO paths with explicit legacy aliases at the repository boundary."""

    def joinpath(self, *pathsegments):
        if Path(self) == ROOT:
            relative = Path(*[str(part).replace("\\", "/") for part in pathsegments])
            if not relative.is_absolute() and relative.parts:
                first, *rest = relative.parts
                if first == "src":
                    return type(self)(CODE.parent, *rest)
                if first in {"uv.lock", "pyproject.toml"}:
                    return type(self)(BACKEND / relative)
                if first == "data":
                    return type(self)(DATA, *rest)
        return super().joinpath(*pathsegments)

    def __truediv__(self, key):
        return self.joinpath(key)

    def relative_to(self, *other, walk_up=False):
        base = Path(*other)
        physical = Path(self)
        if base == ROOT:
            if physical.is_relative_to(CODE):
                return type(self)("src/gabi") / physical.relative_to(CODE)
            if physical.is_relative_to(BACKEND / "src"):
                return type(self)("src") / physical.relative_to(BACKEND / "src")
            if physical.is_relative_to(DATA):
                return type(self)("data") / physical.relative_to(DATA)
            if physical in {BACKEND / "uv.lock", BACKEND / "pyproject.toml"}:
                return type(self)(physical.name)
        return super().relative_to(*other, walk_up=walk_up)


class _LegacyPathLoader(SourceFileLoader):
    def exec_module(self, module):
        super().exec_module(module)
        module.Path = RepositoryPath


class _LegacyPathFinder(MetaPathFinder):
    # These are the only engines that create source manifest keys from __file__.
    names = {"gabi.overfitting_audit", "gabi.full_universe_audit"}

    def find_spec(self, fullname, path=None, target=None):
        if fullname not in self.names:
            return None
        spec = PathFinder.find_spec(fullname, path)
        if spec is not None and isinstance(spec.loader, SourceFileLoader):
            spec.loader = _LegacyPathLoader(fullname, spec.loader.path)
        return spec


def configure(module: ModuleType) -> None:
    """Relocate only config Path constants; original config.py remains byte-identical."""
    previous_data = module.DATA_DIR
    for name, value in list(vars(module).items()):
        if isinstance(value, Path) and value.is_relative_to(previous_data):
            setattr(module, name, RepositoryPath(DATA / value.relative_to(previous_data)))
    setattr(module, "BASE_DIR", RepositoryPath(ROOT))
    if not any(isinstance(finder, _LegacyPathFinder) for finder in sys.meta_path):
        sys.meta_path.insert(0, _LegacyPathFinder())
