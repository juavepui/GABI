"""Atomic local Research defaults; never changes the frozen model or evidence."""

import json
import os
from pathlib import Path
from uuid import uuid4


class FileWeights:
    def __init__(self, data_dir: Path):
        self.path = data_dir / "weights.json"

    def save_weights(self, weights: dict[str, float]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f"weights.{uuid4().hex}.tmp")
        try:
            with temporary.open("x", encoding="utf-8") as stream:
                json.dump(weights, stream, sort_keys=True, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(self.path)
        finally:
            temporary.unlink(missing_ok=True)
