"""Reviewed legacy sources and frozen stability behind shared evidence assessment."""

from collections.abc import Callable
from datetime import UTC, datetime

import pandas as pd

from gabi.application.market.evidence_assessment import build_evidence
from gabi.domain.market.evidence import DEFAULT_RULES, EvidenceRules


class LegacyEvidence:
    def __init__(self, *, now: Callable[[], datetime] | None = None, rules: EvidenceRules = DEFAULT_RULES,
                 benchmark: str = "SPY"):
        self.now = now or (lambda: datetime.now(UTC))
        self.rules, self.benchmark = rules, benchmark

    def evidence(self, table: pd.DataFrame, weights: dict) -> dict[str, dict]:
        from gabi import app_mode, evidence_catalog, live_ledger, rank_stability
        from gabi.history_refresh import last_completed_session

        now = self.now()
        catalogue = evidence_catalog.load()
        return build_evidence(table, weights, now=now, market_date=last_completed_session(now),
                              catalogue=catalogue, matching=evidence_catalog.matches(catalogue, weights, "SP500_CURRENT"),
                              metadata=live_ledger.model_metadata(weights=weights), analyze_stability=rank_stability.analyze,
                              model_id=app_mode.FROZEN_MODEL_ID, benchmark=self.benchmark, rules=self.rules)

    @staticmethod
    def stability(table: pd.DataFrame, weights: dict) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
        from gabi import rank_stability

        return rank_stability.analyze(table, weights)

    @staticmethod
    def perturbations(weights: dict) -> pd.DataFrame:
        from gabi import rank_stability

        return rank_stability.perturbations(weights)
