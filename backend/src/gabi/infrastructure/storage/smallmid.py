"""The #44 test state from its marker files only: frozen data (A3 rule) and the published analysis."""

from collections.abc import Callable
from datetime import date
from pathlib import Path


class SmallmidFiles:
    def __init__(self, data_dir: Path, repo_root: Path, freeze_deadline: Callable[[], str]):
        self.complete = data_dir / "smallmid_test" / "tiingo_completa.json"
        self.result = repo_root / "docs" / "smallmid-test" / "resultado.json"
        self.deadline = freeze_deadline

    def state(self, today: date) -> dict:
        complete, deadline = self.complete.is_file(), self.deadline()
        return {"data_frozen": complete or today.isoformat() >= deadline, "tiingo_complete": complete,
                "freeze_deadline": deadline, "analyzed": self.result.is_file()}
