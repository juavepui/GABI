"""Conservative qualitative evidence, separate from score and weighted coverage."""

from datetime import UTC, datetime

import numpy as np
import pandas as pd

from . import app_mode, config, evidence_catalog, live_ledger, rank_stability, scoring
from .history_refresh import last_completed_session

RULE_VERSION = "evidence-v1"


def _number(value) -> float | None:
    try:
        return float(value) if np.isfinite(float(value)) else None
    except (TypeError, ValueError):
        return None


def factor_components(row: pd.Series, weights: dict, catalogue: dict) -> list[dict]:
    """Decompose the existing available-block mean; never change its weights."""
    available = {b: [(m, _number(row.get(m + "_pct"))) for m in cols] for b, cols in scoring.SCORE_METRICS.items()}
    available = {b: [(m, p) for m, p in values if p is not None] for b, values in available.items()}
    denominator = sum(weights.get(b, 0) for b, values in available.items() if values)
    components = []
    for block, values in available.items():
        for metric, percentile in values:
            assert percentile is not None
            evidence = catalogue.get("factors", {}).get(metric, {})
            mean, p = _number(evidence.get("media")), _number(evidence.get("p_holm"))
            supported = mean is not None and mean > 0 and p is not None and 0 <= p < .05
            weight = weights.get(block, 0) / denominator / len(values) if denominator else 0
            components.append({"metric": metric, "family": block, "percentile": percentile,
                               "supports_candidate": percentile >= 50, "effective_weight": weight,
                               "contribution_points": weight * percentile, "statistically_supported": supported,
                               "mean_ic": mean, "p_holm": p, "classification": evidence.get("classification"),
                               "windows": evidence.get("windows", {}), "sector_stability": evidence.get("sector_stability", {}),
                               "size_stability": evidence.get("size_stability", {}),
                               "sic_division_stability": evidence.get("sic_division_stability", {}),
                               "sic_experiment_id": "factor-zoo-sector" if evidence.get("sic_division_stability") else None,
                               "evidence_stage": "RETROSPECTIVE", "experiment_id": "factor-zoo"})
    return components


def freshness(source: dict, benchmark: dict, *, market_date: str, now: datetime) -> dict:
    stale = []
    for name, inputs in (("empresa", source), ("SPY", benchmark)):
        if inputs.get("price_date") != market_date or any((_number(inputs.get(k)) or 0) <= 0 for k in ("close", "adj_close")):
            stale.append(f"Precio de {name} ausente, caducado o futuro")
    for field, hours in (("fundamentals_fetched_at", config.CACHE_MAX_AGE_HOURS),
                         ("sec_fetched_at", config.EDGAR_CACHE_MAX_AGE_HOURS)):
        try:
            timestamp = datetime.fromisoformat(source[field])
            age = (now - timestamp).total_seconds() / 3600
            if age < 0 or age > hours:
                raise ValueError("fuera del TTL")
        except (KeyError, TypeError, ValueError):
            stale.append(f"{field}: fecha ausente, caducada o futura")
    return {"fresh": not stale, "reasons": stale, "sources": source, "benchmark": benchmark, "market_date": market_date}


def assess(row: pd.Series, weights: dict, *, catalogue: dict, quality: dict, stability: dict,
           trace: dict, model_matches: bool, stage: str = "LIVE_FORWARD") -> dict:
    """Pure rule application. Supplied evidence must already have reviewed provenance.

    Production uses only evidence_catalog.load(); it supplies no independent confirmations.
    This API also permits explicitly supplied synthetic evidence for rule tests.
    """
    if stage not in live_ledger.STAGES:
        raise ValueError("Fase de evidencia inválida.")
    factors = factor_components(row, weights, catalogue)
    validated_weight = sum(f["effective_weight"] for f in factors if f["statistically_supported"])
    validated_points = sum(f["contribution_points"] for f in factors if f["statistically_supported"])
    score, coverage = _number(row.get("composite_score")), _number(row.get("score_coverage"))
    reconstructed = sum(f["contribution_points"] for f in factors)
    decomposition_ok = score is not None and bool(factors) and abs(reconstructed - score) < 1e-8
    decomposition_ok &= all(0 <= f["percentile"] <= 100 for f in factors)
    persistence = _number(stability.get("top20_inclusion"))
    model = catalogue.get("model", {})
    placebos, bootstrap = catalogue.get("placebos", {}), catalogue.get("bootstrap", {})
    gates = {
        "catalogue": (catalogue.get("available") is True, "Catálogo de estudios completo y verificado", "Faltan estudios o sus huellas no coinciden"),
        "model": (model_matches, "Modelo/pesos/universo coinciden con el alcance declarado", "Modelo o universo experimental/no coincidente"),
        "quality": (quality.get("fresh") is True, "Datos actuales con fechas trazables", "Datos caducados, futuros o con fechas desconocidas"),
        "coverage": (coverage is not None and coverage >= .80, "Cobertura del score al menos 80 %", "Cobertura del score inferior al 80 % o desconocida"),
        "stability": (persistence is not None and persistence >= .90, "Top-20 persistente en al menos 90 % de perturbaciones", "Top-20 frágil o estabilidad no estimable"),
        "decomposition": (decomposition_ok, "Contribuciones reproducen el score existente", "No se puede atribuir el score a sus factores disponibles"),
        "factors": (validated_weight >= .50, "Al menos 50 % del peso efectivo tiene apoyo tras Holm", "Menos del 50 % del peso efectivo tiene apoyo tras Holm"),
        "predictive_test": (model.get("pass") is True, "Contraste principal y secundarias corregidas favorables", "Capacidad predictiva del Composite no confirmada"),
        "placebos": (placebos.get("pass") is True, "Controles de robustez concluyentes", "Placebos/robustez insuficientes o inconcluyentes"),
        "bootstrap": (bootstrap.get("pass") is True, "Incertidumbre emparejada favorable al modelo exacto", "Bootstrap emparejado ausente, adverso o inconcluyente"),
    }
    reasons_for = [good for passed, good, _ in gates.values() if passed]
    reasons_against = [bad for passed, _, bad in gates.values() if not passed]
    reasons_against.extend(catalogue.get("errors", []))
    reasons_against.extend(quality.get("reasons", []))
    reasons_against.extend(catalogue.get("limitations", []))
    confirmations = set()
    for confirmation in catalogue.get("independent_confirmations", []):
        p, effect = _number(confirmation.get("p_corrected")), _number(confirmation.get("effect"))
        if (confirmation.get("preregistered") is True and confirmation.get("independent") is True
                and confirmation.get("integrity_ok") is True and confirmation.get("early_unsealed") is False
                and confirmation.get("model_version") == trace.get("model_version") and trace.get("model_version")
                and confirmation.get("dataset_id") and p is not None and 0 <= p < .05 and effect is not None and effect > 0):
            confirmations.add(confirmation["dataset_id"])
    level = "BAJA" if not all(v[0] for v in gates.values()) else "ALTA" if len(confirmations) >= 2 else "MEDIA"
    if len(confirmations) < 2:
        reasons_against.append("No hay dos confirmaciones independientes acreditadas del mismo modelo")
    else:
        reasons_for.append("Dos confirmaciones independientes acreditadas del mismo modelo")
    return live_ledger._safe({"confidence_level": level, "score": score, "score_coverage": coverage,
                              "weighted_data_coverage": _number(row.get("confidence")), "collection_stage": stage,
                              "evidence_stage": "OOS" if level == "ALTA" else "RETROSPECTIVE",
                              "rules": {"version": RULE_VERSION, "sha256": evidence_catalog.RULE_SHA256,
                                        "gates": {k: bool(v[0]) for k, v in gates.items()}},
                              "reasons_for": reasons_for, "reasons_against": reasons_against,
                              "factors": factors, "validated_factor_weight": validated_weight,
                              "validated_contribution_points": validated_points,
                              "validated_score_fraction": validated_points / score if decomposition_ok and score and score > 0 else None,
                              "stability": stability, "quality": quality, "predictive_test": model,
                              "placebos": placebos, "bootstrap": bootstrap, "tail": catalogue.get("tail", {}),
                              "independent_confirmations": sorted(confirmations), "trace": trace,
                              "interpretation": "Categoría conservadora de evidencia; no probabilidad futura ni cambio del ranking."})


def build(frame: pd.DataFrame, weights: dict, *, universe_id="SP500_CURRENT", stage="LIVE_FORWARD",
          now: datetime | None = None, market_date: str | None = None, context: dict | None = None) -> dict[str, dict]:
    """Assess the complete unfiltered ranking, with actual loaded input metadata."""
    now = now or datetime.now(UTC)
    market_date = market_date or last_completed_session(now)
    catalogue = evidence_catalog.load()
    source = frame.attrs.get("sources", {})
    trace = {"model_id": app_mode.FROZEN_MODEL_ID, "universe_id": universe_id, "weights": weights,
             "sources": catalogue.get("sources", {}), "sources_fingerprint": catalogue.get("sources_fingerprint"),
             "data_fingerprint": "signal-inputs-v1:" + live_ledger.fingerprint({"inputs": frame.rename_axis("symbol").reset_index().to_dict("records"),
                                                                               "sources": source}), **(context or {})}
    if not context:
        trace.update(live_ledger.model_metadata(weights=weights, universe_id=universe_id))
    trace["model_id"] = app_mode.FROZEN_MODEL_ID if evidence_catalog.matches(catalogue, weights, universe_id) else "EXPERIMENTAL"
    try:
        _, _, companies = rank_stability.analyze(frame, weights)
        stability = companies.to_dict("index")
    except (ValueError, TypeError, KeyError):
        stability = {}
    matching = evidence_catalog.matches(catalogue, weights, universe_id)
    return {str(symbol): assess(row, weights, catalogue=catalogue,
                               quality=freshness(source.get(symbol, {}), source.get(config.BENCHMARK_SYMBOL, {}), market_date=market_date, now=now),
                               stability=stability.get(str(symbol), {}), trace={**trace, "symbol": str(symbol)}, model_matches=matching, stage=stage)
            for symbol, row in frame.iterrows()}
