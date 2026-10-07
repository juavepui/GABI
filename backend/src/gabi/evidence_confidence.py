"""Compatibility composition for published live-ledger consumers."""
from datetime import UTC, datetime

from gabi.application.market.evidence_assessment import build_evidence
from gabi.domain.market import evidence as rules

from . import app_mode, config, evidence_catalog, live_ledger, rank_stability, scoring
from .history_refresh import last_completed_session

RULE_VERSION = rules.RULE_VERSION
_number = rules._number


def _rules():
    return rules.EvidenceRules(tuple((block, tuple(metrics)) for block, metrics in scoring.SCORE_METRICS.items()),
                               config.CACHE_MAX_AGE_HOURS, config.EDGAR_CACHE_MAX_AGE_HOURS,
                               evidence_catalog.RULE_SHA256)


def factor_components(row, weights, catalogue):
    return rules.factor_components(row, weights, catalogue, rules=_rules())


def freshness(source, benchmark, *, market_date, now):
    return rules.freshness(source, benchmark, market_date=market_date, now=now, rules=_rules())


def assess(row, weights, *, catalogue, quality, stability, trace, model_matches, stage="LIVE_FORWARD"):
    return rules.assess(row, weights, catalogue=catalogue, quality=quality, stability=stability,
                        trace=trace, model_matches=model_matches, stage=stage, rules=_rules())


def build(frame, weights, *, universe_id="SP500_CURRENT", stage="LIVE_FORWARD", now=None,
          market_date=None, context=None):
    now = now or datetime.now(UTC)
    market_date = market_date or last_completed_session(now)
    catalogue = evidence_catalog.load()
    return build_evidence(frame, weights, universe_id=universe_id, stage=stage, now=now, market_date=market_date,
                          catalogue=catalogue, matching=evidence_catalog.matches(catalogue, weights, universe_id),
                          metadata=live_ledger.model_metadata(weights=weights, universe_id=universe_id) if not context else {},
                          analyze_stability=rank_stability.analyze, model_id=app_mode.FROZEN_MODEL_ID,
                          benchmark=config.BENCHMARK_SYMBOL, rules=_rules(), context=context)
