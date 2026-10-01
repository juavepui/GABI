"""Evidence and ranking fragility of the current ranking, as the Streamlit Screener, cartera and ficha showed them.

Both are computed in memory on the cached ranking (no download or write) and cached per ranking
revision and weights; they never change the ranking, its weights or eligibility."""

import threading
from collections.abc import Callable
from typing import Protocol

import pandas as pd

from gabi.application.errors import QueryError
from gabi.application.market.queries import MarketQueries, RankingResult
from gabi.application.research.historical import _json_value
from gabi.domain.market.selection import RankingFilter
from gabi.domain.research.live_ledger import canonical

TOP = 20
RESEARCH_KEYS = ("predictive_test", "placebos", "bootstrap", "tail", "stability", "quality", "rules", "trace")
FACTOR_KEYS = ("metric", "family", "percentile", "supports_candidate", "effective_weight", "contribution_points",
               "statistically_supported", "mean_ic", "p_holm")


class EvidenceMath(Protocol):
    def evidence(self, table: pd.DataFrame, weights: dict) -> dict[str, dict]: ...
    def stability(self, table: pd.DataFrame, weights: dict) -> tuple[dict, pd.DataFrame, pd.DataFrame]: ...
    def perturbations(self, weights: dict) -> pd.DataFrame: ...


def _records(frame: pd.DataFrame, index: str) -> list[dict]:
    return [{index: str(key)} | {str(k): _json_value(v) for k, v in row.items()} for key, row in frame.iterrows()]


class EvidenceQueries:
    def __init__(self, market: MarketQueries, math: EvidenceMath):
        self.market, self.math = market, math
        self._lock = threading.Lock()
        self._cache: dict[tuple, object] = {}

    def _ranking(self, override: dict[str, float] | None) -> RankingResult:
        return self.market.ranking(RankingFilter(hide_no_data=False), limit=1, override=override)

    def _cached(self, kind: str, result: RankingResult, compute: Callable[[], object]) -> object:
        key = (kind, result.snapshot.revision, tuple(sorted(result.model.weights.items())))
        with self._lock:
            if key not in self._cache:
                # One entry per kind: a new ranking revision or new weights replace the previous result.
                self._cache = {k: v for k, v in self._cache.items() if k[0] != kind}
                self._cache[key] = compute()
            return self._cache[key]

    def _evidence(self, override: dict[str, float] | None) -> tuple[RankingResult, dict[str, dict]]:
        result = self._ranking(override)
        evidence = self._cached("evidence", result, lambda: self.math.evidence(result.snapshot.table,
                                                                              dict(result.model.weights)))
        assert isinstance(evidence, dict)
        return result, evidence

    def top(self, override: dict[str, float] | None = None, frozen: bool = False) -> dict:
        """The Top-20 table of the old page: eligible candidates by score, then symbol.

        `frozen` uses the frozen weights in any mode, as the old «Mi cartera» page did for its plan."""
        if frozen and self.market.model().mode == "RESEARCH":
            override = dict(self.market.models.policy.frozen_weights)
        result, evidence = self._evidence(override)
        ordered = sorted(evidence, key=lambda s: (-(evidence[s]["score"] if evidence[s]["score"] is not None else -1), s))
        selected = [s for s in ordered if evidence[s]["score"] is not None
                    and (evidence[s]["score_coverage"] or 0) >= .70][:TOP]
        return {"revision": result.snapshot.revision, "mode": result.model.mode,
                "weights": dict(result.model.weights), "available": bool(evidence),
                "rows": [{"symbol": s, "score": evidence[s]["score"],
                          "weighted_data_coverage": evidence[s]["weighted_data_coverage"],
                          "confidence_level": evidence[s]["confidence_level"],
                          "top20_persistence": evidence[s]["stability"].get("top20_inclusion"),
                          "validated_score_fraction": evidence[s]["validated_score_fraction"]} for s in selected]}

    def _one(self, symbol: str, override: dict[str, float] | None) -> tuple[RankingResult, dict]:
        normalized = symbol.strip().upper().replace(".", "-")
        result, evidence = self._evidence(override)
        if normalized not in evidence:
            raise QueryError("company_not_found", "La empresa no está en el universo local cacheado.", 404)
        return result, evidence[normalized]

    def company(self, symbol: str, override: dict[str, float] | None = None) -> dict:
        result, e = self._one(symbol, override)
        factors = [{key: factor[key] for key in FACTOR_KEYS}
                   | {"sic_division_stability": [{"group": group} | values for group, values
                                                 in (factor.get("sic_division_stability") or {}).items()]}
                   for factor in e["factors"]]
        detail = {"symbol": e["trace"]["symbol"], "revision": result.snapshot.revision, "mode": result.model.mode,
                  "confidence_level": e["confidence_level"], "score": e["score"], "score_coverage": e["score_coverage"],
                  "weighted_data_coverage": e["weighted_data_coverage"], "reasons_for": e["reasons_for"],
                  "reasons_against": e["reasons_against"], "factors": factors,
                  "validated_score_fraction": e["validated_score_fraction"],
                  "top20_persistence": e["stability"].get("top20_inclusion"),
                  "collection_stage": e["collection_stage"], "evidence_stage": e["evidence_stage"],
                  "rules_version": e["rules"]["version"], "interpretation": e["interpretation"],
                  "research_details": None}
        if result.model.mode == "RESEARCH":  # As the old page: the full JSON blocks only in Research.
            detail["research_details"] = {key: e[key] for key in RESEARCH_KEYS}
        return detail

    def download(self, symbol: str, override: dict[str, float] | None = None) -> str:
        _, e = self._one(symbol, override)
        return canonical(e)

    def stability(self, override: dict[str, float] | None = None) -> dict:
        result = self._ranking(override)
        weights = dict(result.model.weights)

        def compute() -> object:
            try:
                return self.math.stability(result.snapshot.table, weights)
            except ValueError as exc:
                return str(exc)

        value = self._cached("stability", result, compute)
        base = {"revision": result.snapshot.revision, "mode": result.model.mode, "weights": weights}
        if isinstance(value, str):
            return base | {"available": False, "message": f"Estabilidad no disponible: {value}", "summary": None,
                           "companies": [], "metrics": [], "perturbations": []}
        assert isinstance(value, tuple)
        summary, metrics, companies = value
        research = result.model.mode == "RESEARCH"
        shown = companies if research else companies[companies.base_rank <= TOP]
        return base | {
            "available": True, "message": None,
            "summary": {key: _json_value(summary[key]) for key in ("eligible", "excluded", "perturbations",
                                                                  "omitted_infeasible", "stability_score",
                                                                  "sectors_complete", "interpretation")},
            "companies": _records(shown, "symbol"),
            "metrics": _records(metrics, "perturbation") if research else [],
            "perturbations": _records(self.math.perturbations(weights), "perturbation") if research else [],
        }
