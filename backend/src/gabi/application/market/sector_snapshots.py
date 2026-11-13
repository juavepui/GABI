"""Point-in-time sector lookup over explicit identity and snapshot ports; no schema writes or downloads."""

from typing import Protocol

import pandas as pd

from gabi.domain.market import sector_snapshots as rules


class IdentityPort(Protocol):
    def resolve(self, symbol: str, as_of: str) -> dict: ...
    def observations(self, entity_id: str, dataset: str) -> pd.DataFrame: ...
    def has_aliases(self, symbol: str) -> bool: ...


class SnapshotReader(Protocol):
    def rows(self, symbols: list[str]) -> list[tuple]: ...


def sector_as_of(identity: IdentityPort, snapshots: SnapshotReader, symbols: list[str], as_of: str, *,
                 strict_identity: bool = False) -> dict[str, dict]:
    """Attributed issuers use their own observations; only symbols without any alias read the
    legacy ticker table (never in strict mode), so a recycled ticker cannot cross companies."""
    result = {symbol: rules.unknown() for symbol in symbols}
    legacy = []
    for symbol in symbols:
        resolved = identity.resolve(symbol, as_of)
        if resolved["entity_id"]:
            frame = identity.observations(resolved["entity_id"], "sector")
            if not frame.empty:
                result[symbol] = rules.from_observations(frame, as_of)
        elif not strict_identity and not identity.has_aliases(symbol):
            legacy.append(symbol)
    if legacy:
        result.update(rules.from_symbol_rows(snapshots.rows(legacy), as_of))
    return result
