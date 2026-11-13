"""Code and environment provenance of a research run: git commit, package versions and lockfile hash."""

import hashlib
import subprocess
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


def git_commit(checkout: Path) -> str | None:
    """Short commit of the checkout; None outside git or when git is unavailable."""
    try:
        result = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=checkout,
                                capture_output=True, text=True, timeout=5)
        return result.stdout.strip() or None
    except Exception:
        return None


def working_tree_modified(checkout: Path, pathspec: str) -> bool | None:
    """Uncommitted changes under ``pathspec``; None when git cannot be started."""
    try:
        return bool(subprocess.run(["git", "status", "--porcelain", "--", pathspec], cwd=checkout,
                                   capture_output=True, text=True, timeout=5).stdout)
    except OSError:
        return None


def dependency_versions(packages: list[str]) -> dict:
    """Installed versions of the listed packages; absent packages are omitted."""
    versions = {}
    for package in packages:
        try:
            versions[package] = version(package)
        except PackageNotFoundError:
            pass
    return versions


def lock_fingerprint(lock: Path) -> str | None:
    """First 12 hex characters of the lockfile SHA-256; None if it cannot be read."""
    try:
        return hashlib.sha256(lock.read_bytes()).hexdigest()[:12]
    except OSError:
        return None
