"""The prospective plan's existing JSON bytes, in a supplied output directory."""

import json
from pathlib import Path

from gabi.domain.research.prospective_plan import json_value


class FileProspectivePlans:
    def __init__(self, directory: Path):
        self.directory = directory

    def save(self, name: str, payload: dict) -> None:
        if name not in {"plan.json", "gabi-id1.json"}:
            raise ValueError("Unknown prospective plan artifact")
        self.directory.mkdir(parents=True, exist_ok=True)
        (self.directory / name).write_text(json.dumps(json_value(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
