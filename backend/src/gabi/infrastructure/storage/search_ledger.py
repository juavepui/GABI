"""Repository files for the published search ledger: verify it or write a new revision, never overwrite."""
import json
from collections.abc import Callable
from pathlib import Path

from gabi.domain.research import search_ledger


def reader(root: Path) -> Callable[[str], str]:
    return lambda name: (root / name).read_text(encoding="utf-8")


def build(root: Path) -> dict:
    return search_ledger.build(reader(root))


def verify(root: Path, published: Path | None = None) -> None:
    path = published or root / search_ledger.PUBLISHED
    search_ledger.verify(json.loads(path.read_text(encoding="utf-8")), reader(root))


def write(root: Path, destination: Path) -> dict:
    ledger = build(root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(ledger, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    return ledger
