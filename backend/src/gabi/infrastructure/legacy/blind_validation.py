"""The blind forward validation's public names over its use case, with the configured database.

The path is read per operation (ADR 0005); the ranking is the existing ``screener_asof`` one and
exports go to the existing research lab, both looked up on each call.
"""

from datetime import date

import pandas as pd

from gabi.application.market import cached_data
from gabi.application.research.blind_ledger import BlindLedger
from gabi.infrastructure.providers import research_environment
from gabi.infrastructure.storage.blind_ledger import SCHEMA as SCHEMA
from gabi.infrastructure.storage.blind_ledger import DuplicatePeriod, SqliteBlindLedger
from gabi.infrastructure.storage.cache_reads import SqliteCacheReads


def _current_git_commit() -> str | None:
    from gabi import config

    return research_environment.git_commit(config.BASE_DIR)


def ledger() -> BlindLedger:
    from gabi import config, research_lab, screener_asof

    path = config.DB_PATH
    return BlindLedger(
        SqliteBlindLedger(path),
        ranking=lambda as_of, weights: screener_asof.build_ranking_as_of(as_of, weights=weights)["table"],
        prices=lambda symbols: cached_data.prices_multi(SqliteCacheReads(path), symbols),
        git_commit=lambda: _current_git_commit(), today=lambda: date.today(),
        timestamp=lambda: pd.Timestamp.now().isoformat(),
        log_experiment=lambda *args, **kwargs: research_lab.log_experiment(*args, **kwargs),
        duplicate=DuplicatePeriod)


def create_validation(name: str, weights: dict, n_positions: int, rebalance_months: int,
                      start_date: str, unlock_date: str, model_id: str = "GABI-MF-v1") -> int:
    return ledger().create_validation(name, weights, n_positions, rebalance_months, start_date, unlock_date,
                                      model_id)


def record_rebalance(validation_id: int, as_of: str | None = None) -> dict:
    return ledger().record_rebalance(validation_id, as_of)


def enable_ranking_snapshots(validation_id: int) -> None:
    ledger().enable_ranking_snapshots(validation_id)


def verify_integrity(validation_id: int) -> dict:
    return ledger().verify_integrity(validation_id)


def get_status(validation_id: int, reveal: bool = False, as_of: str | None = None) -> dict:
    return ledger().get_status(validation_id, reveal, as_of)


def break_seal_early(validation_id: int, reason: str) -> None:
    ledger().break_seal_early(validation_id, reason)


def list_validations() -> pd.DataFrame:
    return ledger().list_validations()


def export_to_research_lab(validation_id: int, as_of: str | None = None) -> int:
    return ledger().export_to_research_lab(validation_id, as_of)


def _mark_to_market_return(symbols: list, entry_prices: dict, as_of_ts: pd.Timestamp) -> float | None:
    return ledger().mark_to_market_return(symbols, entry_prices, as_of_ts)
