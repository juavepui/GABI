"""Public name cited by the sealed preregistration of #43 (``value_hypothesis.spec_hash()``).

Thin adapter kept by ADR 0002: the specification lives in
``gabi.domain.research.value_hypothesis`` and the preregistration in ``gabi_cli research``.
"""

from gabi.domain.research import value_hypothesis as _hypothesis

from . import scoring

SPEC = _hypothesis.specification(scoring.SCORE_METRICS["value"])


def spec_hash() -> str:
    return _hypothesis.spec_hash(SPEC)
