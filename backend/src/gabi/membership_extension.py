"""Replay reviewed, dated index changes; never infer past members from today's list."""
from datetime import date

import pandas as pd

from gabi.domain.research import membership
from gabi.domain.research.membership import fingerprint as fingerprint
from gabi.domain.research.membership import symbols as symbols
from gabi.infrastructure.storage import reviewed_resources

LEDGER_PATH = reviewed_resources.MEMBERSHIP_LEDGER


def reviewed_through() -> str:
    return str(reviewed_resources.membership_ledger()["verified_through"])


def extend_membership(history: pd.DataFrame, ledger: dict) -> pd.DataFrame:
    return membership.extend_membership(history, ledger, today=date.today())


def apply_reviewed_extension(history: pd.DataFrame) -> pd.DataFrame:
    return membership.apply_reviewed_extension(history, reviewed_resources.membership_ledger(), today=date.today())
