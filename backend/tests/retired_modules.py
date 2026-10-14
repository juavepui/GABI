"""Stand-ins for the flat modules retired in F7 (#90/#91), for captured sources run outside pytest.

Parity tests inject only the module a capture needs, with ``monkeypatch.setitem``. Measuring
scripts call :func:`install` before executing a captured module. Production code never sees
these: a retired name only resolves where it was installed explicitly.
"""

import sys
from datetime import UTC, datetime
from types import ModuleType


def _module(name: str, **names) -> ModuleType:
    module = ModuleType(f"gabi.{name}")
    module.__dict__.update(names)
    return module


def facades() -> dict[str, ModuleType]:
    """``insider`` and ``macro`` (F7.25): the readers captured sources used, over the same stores."""
    from gabi import config
    from gabi.domain.market import fred
    from gabi.infrastructure.storage.fred import SqliteFred
    from gabi.infrastructure.storage.insiders import SqliteInsiders

    def series():
        return SqliteFred(config.DB_PATH, lambda: datetime.now(UTC))

    return {
        "insider": _module("insider", get_insider_fetched_at=lambda symbols: SqliteInsiders(
            config.DB_PATH.parent, database=config.DB_PATH).fetched_at(symbols)),
        "macro": _module("macro", SERIES={key: dict(value) for key, value in fred.SERIES.items()},
                         get_all_fetched_at=lambda: series().fetched_at_all(),
                         get_series_history=lambda series_id: series().history(series_id)),
    }


def stand_ins() -> dict[str, ModuleType]:
    import sync_checkpoints

    from gabi.domain.market.price_sync import COLS
    from gabi.infrastructure.legacy import (
        blind_validation,
        data_fetch,
        data_quality,
        historical_identity_audit,
        history_refresh,
        sec_history,
    )
    from gabi.infrastructure.storage.readonly import connect_readonly

    return {
        **facades(),
        "blind_validation": blind_validation,
        "data_fetch": data_fetch,
        "data_quality": data_quality,
        "historical_identity_audit": historical_identity_audit,
        "history_refresh": history_refresh,
        "sec_history": sec_history,
        "sync_state": sync_checkpoints,
        "price_sync": _module("price_sync", run=data_fetch.sync_prices, COLS=COLS),
        # Retired in #138; captured sources imported only its read-only connection helper.
        "historical_data_audit": _module("historical_data_audit", connect_readonly=connect_readonly),
    }


def install() -> None:
    """Make every retired ``gabi.<name>`` importable in this process (measuring scripts only)."""
    sys.modules.update({f"gabi.{name}": module for name, module in stand_ins().items()})
