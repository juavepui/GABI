"""Legacy quality persistence; pure calculations live in domain."""

import gabi.domain.market.quality_persistence as _implementation
from gabi.application.market.quality import quality_as_of

from . import edgar

_annual = _implementation._annual
_ratio = _implementation._ratio
_summary = _implementation._summary
_cagr = _implementation._cagr
from_facts = _implementation.from_facts

def as_of(symbol: str, as_of_date: str, *, entity_id: str | None = None) -> dict:
    """Calcula las métricas con solo los hechos presentados hasta ``as_of``."""
    return quality_as_of(symbol, as_of_date, read_facts=edgar._facts_dict_from_stored,
                         entity_id=entity_id)
