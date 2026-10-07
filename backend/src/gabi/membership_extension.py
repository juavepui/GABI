"""Replay reviewed, dated index changes; never infer past members from today's list."""
import json
from datetime import date
from pathlib import Path

import pandas as pd

from gabi.domain.research import membership
from gabi.domain.research.membership import fingerprint as fingerprint
from gabi.domain.research.membership import symbols as symbols

LEDGER_PATH = Path(__file__).with_name("resources") / "sp500_extension.json"


def reviewed_through() -> str:
    return str(json.loads(LEDGER_PATH.read_text(encoding="utf-8"))["verified_through"])


def extend_membership(history: pd.DataFrame, ledger: dict) -> pd.DataFrame:
    return membership.extend_membership(history, ledger, today=date.today())


def apply_reviewed_extension(history: pd.DataFrame) -> pd.DataFrame:
    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    return membership.apply_reviewed_extension(history, ledger, today=date.today())
