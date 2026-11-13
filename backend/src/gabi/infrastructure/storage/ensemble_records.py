"""Prospective ENS records (#237): one canonical JSON per quarter in the repository, never overwritten."""

import json
import re
from pathlib import Path

NAME = re.compile(r"registro-(\d{4}-\d{2}-\d{2})\.json")


class FileEnsembleRecords:
    def __init__(self, directory: Path, *, max_files: int = 200, max_bytes: int = 16 * 1024 * 1024):
        self.directory, self.max_files, self.max_bytes = directory, max_files, max_bytes

    def all(self) -> list[dict]:
        if not self.directory.is_dir():
            return []
        paths = sorted(path for path in self.directory.iterdir() if NAME.fullmatch(path.name))
        if len(paths) > self.max_files:
            raise ValueError("El registro prospectivo supera el límite de ficheros.")
        records = []
        for path in paths:
            if path.stat().st_size > self.max_bytes:
                raise ValueError(f"Registro prospectivo demasiado grande: {path.name}")
            record = json.loads(path.read_text(encoding="utf-8"))
            if record.get("signal_date") != path.stem.removeprefix("registro-"):
                raise ValueError(f"Fecha del registro distinta de su nombre: {path.name}")
            records.append(record)
        return records

    def write(self, record: dict) -> str:
        path = self.directory / f"registro-{record['signal_date']}.json"
        self.directory.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8", newline="\n") as stream:  # never overwrite a sealed quarter
            stream.write(json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
        return str(path)
