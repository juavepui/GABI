"""Shared evidence assessment for a full ranking and explicit reviewed inputs."""
from collections.abc import Callable
from datetime import datetime

import pandas as pd

from gabi.domain.market.evidence import DEFAULT_RULES, EvidenceRules, assess, freshness
from gabi.domain.research.live_ledger import fingerprint


def build_evidence(frame: pd.DataFrame, weights: dict, *, universe_id="SP500_CURRENT", stage="LIVE_FORWARD",
          now: datetime, market_date: str, catalogue: dict, matching: bool, metadata: dict,
          analyze_stability: Callable[[pd.DataFrame, dict], tuple], model_id: str, benchmark: str,
          rules: EvidenceRules = DEFAULT_RULES, context: dict | None = None) -> dict[str, dict]:
    """Assess the complete unfiltered ranking, with actual loaded input metadata."""
    source = frame.attrs.get("sources", {})
    trace = {"model_id": model_id, "universe_id": universe_id, "weights": weights,
             "sources": catalogue.get("sources", {}), "sources_fingerprint": catalogue.get("sources_fingerprint"),
             "data_fingerprint": "signal-inputs-v1:" + fingerprint({"inputs": frame.rename_axis("symbol").reset_index().to_dict("records"),
                                                                               "sources": source}), **(context or {})}
    if not context:
        trace.update(metadata)
    trace["model_id"] = model_id if matching else "EXPERIMENTAL"
    try:
        _, _, companies = analyze_stability(frame, weights)
        stability = companies.to_dict("index")
    except (ValueError, TypeError, KeyError):
        stability = {}
    return {str(symbol): assess(row, weights, catalogue=catalogue,
                               quality=freshness(source.get(symbol, {}), source.get(benchmark, {}), market_date=market_date, now=now, rules=rules),
                               stability=stability.get(str(symbol), {}), trace={**trace, "symbol": str(symbol)}, model_matches=matching, stage=stage, rules=rules)
            for symbol, row in frame.iterrows()}
