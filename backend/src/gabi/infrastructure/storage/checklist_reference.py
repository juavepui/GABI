"""Packaged pass-rate reference of the Checklist (#171), written by `gabi_cli market checklist-coverage --reference`."""

import json
from functools import cache
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "resources" / "checklist_reference.json"
MAX_BYTES = 2 * 1024 * 1024


@cache
def load_checklist_reference(path: Path = DEFAULT_PATH) -> dict | None:
    """The reference read once per process; a missing, oversized or malformed file means no reference."""
    try:
        if path.stat().st_size > MAX_BYTES:
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("criteria"), dict):
        return None
    return payload
