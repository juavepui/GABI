"""Atomic local mode selection, compatible with Streamlit's app_mode.json."""

import json
import os
from pathlib import Path
from uuid import uuid4


class FileMode:
    def __init__(self, data_dir: Path):
        self.path = data_dir / "app_mode.json"

    def save_mode(self, mode: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f"app_mode.{uuid4().hex}.tmp")
        try:
            with temporary.open("x", encoding="utf-8") as stream:
                json.dump({"mode": mode}, stream)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(self.path)
        finally:
            temporary.unlink(missing_ok=True)
