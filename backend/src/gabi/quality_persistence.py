"""Métricas point-in-time para estudiar la persistencia de la calidad.

Este módulo es deliberadamente descriptivo: no cambia el Composite congelado
ni decide pesos. Reutiliza los hechos anuales de EDGAR ya filtrados por
``filed_date`` para que una futura variante pueda compararse con el ranking
actual sin introducir look-ahead.
"""
from datetime import date

import numpy as np

from . import edgar


def _annual(facts: dict, tags: list[str]) -> dict[str, float]:
    return dict(edgar._extract_annual_values(facts, tags))


def _ratio(numerator: dict[str, float], denominator: dict[str, float], *, positive_denominator: bool = True):
    result = {}
    for key in sorted(set(numerator) & set(denominator)):
        den = denominator[key]
        if den is None or (positive_denominator and den <= 0):
            continue
        result[key] = float(numerator[key] / den)
    return result


def _summary(values: dict[str, float], *, positive: bool = False) -> dict[str, float | int | None]:
    numbers = np.asarray(list(values.values()), dtype=float)
    numbers = numbers[np.isfinite(numbers)]
    if not len(numbers):
        return {"mean": None, "std": None, "positive_years": 0, "years": 0}
    return {
        "mean": float(numbers.mean()),
        "std": float(numbers.std(ddof=1)) if len(numbers) > 1 else 0.0,
        "positive_years": int((numbers > 0).sum()) if positive else None,
        "years": int(len(numbers)),
    }


def _cagr(values: dict[str, float]) -> float | None:
    valid = [(date.fromisoformat(k), v) for k, v in values.items() if v and v > 0]
    valid.sort()
    if len(valid) < 2:
        return None
    start_date, start_value = valid[0]
    end_date, end_value = valid[-1]
    years = (end_date - start_date).days / 365.25
    return float((end_value / start_value) ** (1 / years) - 1) if years > 0 else None


def from_facts(facts: dict) -> dict:
    """Calcula persistencia anual a partir de hechos EDGAR ya point-in-time.

    Las métricas devueltas son observables, no una señal de inversión: medias,
    dispersión, años positivos y crecimiento por acción. Las series con menos
    de dos años conservan sus recuentos, pero no se presentan como estabilidad.
    """
    revenue = _annual(facts, edgar.REVENUE_TAGS)
    net_income = _annual(facts, edgar.NET_INCOME_TAGS)
    operating_income = _annual(facts, edgar.OPERATING_INCOME_TAGS)
    ocf = _annual(facts, edgar.OCF_TAGS)
    capex = _annual(facts, edgar.CAPEX_TAGS)
    equity = dict(edgar._extract_instant_values(facts, edgar.EQUITY_TAGS))
    debt = dict(edgar._extract_instant_values(facts, edgar.LT_DEBT_TAGS))
    shares = dict(edgar._extract_instant_values(facts, edgar.SHARES_TAGS, unit="shares"))

    invested_capital = {k: equity[k] + debt[k] for k in set(equity) & set(debt)
                        if equity[k] + debt[k] > 0}
    roic = _ratio(net_income, invested_capital)
    margin = _ratio(operating_income, revenue)
    fcf = {k: ocf[k] - abs(capex[k]) for k in set(ocf) & set(capex)}
    fcf_conversion = _ratio(fcf, revenue)
    revenue_per_share = _ratio(revenue, shares)

    roic_summary = _summary(roic, positive=True)
    margin_summary = _summary(margin, positive=True)
    fcf_summary = _summary(fcf_conversion, positive=True)
    def _positive_fraction(summary: dict[str, float | int | None]) -> float | None:
        years = summary["years"]
        positive_years = summary["positive_years"]
        if not years or positive_years is None:
            return None
        return float(positive_years) / float(years)

    score_parts = [_positive_fraction(roic_summary), _positive_fraction(margin_summary), _positive_fraction(fcf_summary)]
    available_parts = [x for x in score_parts if x is not None]
    return {
        "roic_persistence_mean": roic_summary["mean"],
        "roic_persistence_std": roic_summary["std"],
        "roic_positive_years": roic_summary["positive_years"],
        "roic_years": roic_summary["years"],
        "operating_margin_persistence_mean": margin_summary["mean"],
        "operating_margin_persistence_std": margin_summary["std"],
        "operating_margin_positive_years": margin_summary["positive_years"],
        "operating_margin_years": margin_summary["years"],
        "fcf_conversion_mean": fcf_summary["mean"],
        "fcf_conversion_std": fcf_summary["std"],
        "fcf_positive_years": fcf_summary["positive_years"],
        "fcf_years": fcf_summary["years"],
        "revenue_per_share_cagr": _cagr(revenue_per_share),
        "quality_persistence_score": float(np.mean(available_parts)) if available_parts else None,
    }


def as_of(symbol: str, as_of_date: str, *, entity_id: str | None = None) -> dict:
    """Calcula las métricas con solo los hechos presentados hasta ``as_of``."""
    return from_facts(edgar._facts_dict_from_stored(symbol, as_of_date, entity_id=entity_id))
