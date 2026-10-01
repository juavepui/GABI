"""Candidate evidence and ranking stability through the unchanged evidence_confidence/rank_stability."""

import pandas as pd


class LegacyEvidence:
    @staticmethod
    def evidence(table: pd.DataFrame, weights: dict) -> dict[str, dict]:
        from gabi import evidence_confidence

        return evidence_confidence.build(table, weights)

    @staticmethod
    def stability(table: pd.DataFrame, weights: dict) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
        from gabi import rank_stability

        return rank_stability.analyze(table, weights)

    @staticmethod
    def perturbations(weights: dict) -> pd.DataFrame:
        from gabi import rank_stability

        return rank_stability.perturbations(weights)
