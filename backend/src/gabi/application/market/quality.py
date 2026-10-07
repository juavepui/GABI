"""Quality evidence from an explicitly bounded, point-in-time facts reader."""

from collections.abc import Callable

from gabi.domain.market.quality_persistence import from_facts


def quality_as_of(symbol: str, as_of_date: str, *, read_facts: Callable[..., dict],
                  entity_id: str | None = None) -> dict:
    return from_facts(read_facts(symbol, as_of_date, entity_id=entity_id))
