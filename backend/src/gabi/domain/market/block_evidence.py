"""Retrospective evidence of each score block (#185), grouped from the published Factor Zoo; never recomputed.

A block gathers the evidence of its scored metrics. Its classification is the strongest one any of its
metrics reached, always shown with how many metrics reached it, so one weak hint is never read as a
supported block. The mean IC of a block is the plain mean of its metrics' mean ICs, a description and
not a new test. Weights, selection and the frozen hypothesis are untouched.
"""

import math
from collections.abc import Mapping

from gabi.domain.market.scoring import SCORE_METRICS
from gabi.domain.research import labels

ORDER = ("sin_evidencia", "indicio", "requiere_OOS", "robusta_retrospectivamente")


def _number(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def blocks(factors: Mapping[str, Mapping], score_metrics: Mapping[str, list[str]] = SCORE_METRICS) -> list[dict]:
    """One row per block, with each scored metric's mean IC, Holm p-value and classification."""
    result = []
    for block, names in score_metrics.items():
        metrics = []
        for name in names:
            factor = factors.get(name)
            code = None if factor is None else str(factor.get("classification"))
            if code is not None and code not in ORDER:
                raise ValueError(f"Clasificación publicada desconocida: {code}")
            metrics.append({"metric": name, "published": factor is not None,
                            "ic_mean": None if factor is None else _number(factor.get("media")),
                            "p_holm": None if factor is None else _number(factor.get("p_holm")),
                            "classification": code,
                            "classification_label": None if code is None else labels.factor_classification(code)[0]})
        codes = [row["classification"] for row in metrics if row["classification"] is not None]
        best = max(codes, key=ORDER.index) if codes else None
        ics = [row["ic_mean"] for row in metrics if row["ic_mean"] is not None]
        result.append({
            "block": block, "metrics": metrics,
            "classification": best,
            "classification_label": None if best is None else labels.factor_classification(best)[0],
            "metrics_at_classification": sum(code == best for code in codes) if best else 0,
            "metrics_with_evidence": sum(code != "sin_evidencia" for code in codes),
            "metrics_published": len(codes),
            "ic_mean": sum(ics) / len(ics) if ics else None,
            "holm_significant": sum(row["p_holm"] is not None and row["p_holm"] < .05 for row in metrics),
        })
    return result
