"""Local Checklist threshold edits (#167); defaults live in the domain and never change the Composite."""

import json
import os
from pathlib import Path
from uuid import uuid4

SCHEMA_VERSION = 1
MAX_BYTES = 64 * 1024


class FileChecklistThresholds:
    def __init__(self, data_dir: Path):
        self.path = data_dir / "checklist_thresholds.json"

    def load(self) -> tuple[dict, str | None]:
        """Saved edits and a warning code; a missing file means the Excel defaults."""
        if not self.path.is_file():
            return {}, None
        try:
            if self.path.stat().st_size > MAX_BYTES:
                return {}, "invalid_saved_thresholds"
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}, "invalid_saved_thresholds"
        if not isinstance(payload, dict) or payload.get("version") != SCHEMA_VERSION \
                or not isinstance(payload.get("values"), dict):
            return {}, "invalid_saved_thresholds"
        return payload["values"], None

    def save(self, overrides: dict[str, float]) -> None:
        if not overrides:
            self.reset()
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f"checklist_thresholds.{uuid4().hex}.tmp")
        try:
            with temporary.open("x", encoding="utf-8") as stream:
                json.dump({"version": SCHEMA_VERSION, "values": overrides}, stream, sort_keys=True,
                          allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(self.path)
        finally:
            temporary.unlink(missing_ok=True)

    def reset(self) -> None:
        self.path.unlink(missing_ok=True)
