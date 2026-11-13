"""Evidence of the score blocks (#185) for the ranking, the company page and the target portfolio.

Read-only presentation of the published, sealed Factor Zoo: the reader verifies its hashes and caches it
while the files do not change. Nothing is recomputed per request and no weight changes.
"""

from collections.abc import Callable

from gabi.application.errors import QueryError
from gabi.domain.market import block_evidence


class BlockEvidence:
    def __init__(self, read: Callable[[], dict], weights: Callable[[], dict[str, float]]):
        """`read()` is the verified published Factor Zoo; `weights()` the frozen block weights."""
        self.read, self.weights = read, weights

    def summary(self) -> dict:
        verified = self.read()
        try:
            zoo = verified["zoo"]
            blocks = block_evidence.blocks(zoo["factors"])
            weights = self.weights()
            return {"status": "RETROSPECTIVE_DESCRIPTIVE", "independent_advantage_demonstrated": False,
                    "catalog": "factor-zoo", "catalog_sha256": verified["zoo_sha256"], "n_dates": zoo["n_dates"],
                    "holm_significant_count": sum(row["holm_significant"] for row in blocks),
                    "blocks": [row | {"frozen_weight": float(weights.get(row["block"], 0))} for row in blocks]}
        except (KeyError, TypeError, ValueError) as exc:
            raise QueryError("published_factors_unavailable",
                             "El mapa de factores publicado tiene una estructura inesperada.", 503) from exc
