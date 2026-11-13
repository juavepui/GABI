"""Ingresos, beneficio neto y caja libre por ejercicio (#328, parte B), from the SEC annual reports.

Reuses the tag selection and fiscal-year alignment of ``sec_facts`` (the same ones behind the metrics):
the revenue candidates (``REVENUE_TAGS``) are bridged only when they reconcile, only complete annual
periods of a 10-K count, the latest filing of a period wins (restatements), and the other figures belong
to the revenue year-end within ``ALIGNMENT_TOLERANCE_DAYS`` (a company whose year ends in September is
read by its own year-end, never forced to the calendar year). Free cash flow is operating cash flow minus
capital expenditure, as in ``compute_edgar_metrics``.

Descriptive only: the figures are shown, never used in an analysis, so periods after the reserved date
(2025-07-02) may appear here. Amounts are in US dollars, as the company reported them to the SEC.
"""

import math
from datetime import date

from gabi.domain.market.sec_facts import (
    ALIGNMENT_TOLERANCE_DAYS,
    CAPEX_TAGS,
    NET_INCOME_TAGS,
    OCF_TAGS,
    REVENUE_TAGS,
    _at_anchor,
    _extract_annual_values,
)

TAGS = REVENUE_TAGS + NET_INCOME_TAGS + OCF_TAGS + CAPEX_TAGS
YEARS = 5
MONTHS = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")
MISSING = {
    "revenue": "No hay ingresos de este ejercicio que GABI pueda leer con seguridad: la empresa no los declaró "
               "o usó una etiqueta distinta de la de otros años que no se puede enlazar con ella.",
    "net_income": "La empresa no declaró su beneficio neto de este ejercicio en el informe anual.",
    "free_cash_flow": "Falta el dinero que generó su negocio o lo que invirtió ese ejercicio, así que no se "
                      "puede calcular su caja libre.",
}


def _filed(facts: dict, tags: list[str], end: str, value: float) -> str | None:
    """Publication date of the filing whose figure is shown: the latest 10-K reporting that value."""
    found = []
    for tag in tags:
        for entry in facts.get("facts", {}).get("us-gaap", {}).get(tag, {}).get("units", {}).get("USD", []):
            if (entry.get("form") in {"10-K", "10-K/A"} and entry.get("fp") == "FY" and entry.get("end") == end
                    and entry.get("val") is not None and entry.get("filed")
                    and abs(float(entry["val"]) - value) <= 0.01 * max(abs(value), 1.0)):
                found.append(str(entry["filed"])[:10])
    return max(found) if found else None


def _series(facts: dict, tags: list[str]) -> dict[str, tuple[float, str | None]]:
    return {end: (float(value), _filed(facts, tags, end, float(value)))
            for end, value in _extract_annual_values(facts, tags)}


def label(end: str) -> str:
    """«2024» for a year that ends in December; otherwise the month it closes («sep 2024»).

    A 52/53-week year can end in the first days of the next month (WDC: 3 Jul 2026 closes its June
    year), so a year-end in the first week is named by the month before."""
    day = date.fromisoformat(end)
    if day.day <= 7:
        day = date(day.year - 1, 12, 31) if day.month == 1 else date(day.year, day.month - 1, 1)
    return str(day.year) if day.month == 12 else f"{MONTHS[day.month - 1]} {day.year}"


def _restated(facts: dict, filed: str | None) -> bool:
    """True when a later annual report gave another revenue or net income for a year this report also gave:
    the company redid its figures afterwards (a sale of a business, an accounting change), so this row's
    figures are not on the same basis as the newer ones."""
    if not filed:
        return False
    reports: dict[tuple[str, str], dict[str, float]] = {}
    for tag in REVENUE_TAGS + NET_INCOME_TAGS:
        kind = "revenue" if tag in REVENUE_TAGS else "net_income"
        for entry in facts.get("facts", {}).get("us-gaap", {}).get(tag, {}).get("units", {}).get("USD", []):
            if (entry.get("form") in {"10-K", "10-K/A"} and entry.get("fp") == "FY" and entry.get("filed")
                    and entry.get("start") and entry.get("end") and entry.get("val") is not None
                    and 340 <= (date.fromisoformat(entry["end"]) - date.fromisoformat(entry["start"])).days <= 380):
                reports.setdefault((str(entry["filed"])[:10], kind), {}).setdefault(entry["end"], float(entry["val"]))
    for (day, kind), own in reports.items():
        if day != filed:
            continue
        for (later, other_kind), newer in reports.items():
            if later > day and other_kind == kind and any(
                    end in newer and abs(newer[end] - value) > 0.01 * max(abs(value), 1.0)
                    for end, value in own.items()):
                return True
    return False


def money(value: float) -> str:
    """Millions of dollars in Spanish: «391.035 millones de $»."""
    millions = abs(value) / 1e6
    text = f"{millions:,.0f}" if millions >= 10 else f"{millions:,.1f}"
    return text.replace(",", "_").replace(".", ",").replace("_", ".") + " millones de $"


def _percent(value: float) -> str:
    return f"{value * 100:.1f}".replace(".", ",") + " %"


def rows(facts: dict, years: int = YEARS) -> list[dict]:
    """The last `years` fiscal years with a revenue (or, without revenue, net income) figure, oldest first."""
    revenue = _series(facts, REVENUE_TAGS)
    net_income = _series(facts, NET_INCOME_TAGS)
    ocf = dict(_extract_annual_values(facts, OCF_TAGS))
    capex = dict(_extract_annual_values(facts, CAPEX_TAGS))
    fcf = {end: (ocf[end] - abs(capex[end]),
                 max(filter(None, (_filed(facts, OCF_TAGS, end, ocf[end]), _filed(facts, CAPEX_TAGS, end, capex[end]))),
                     default=None))
           for end in set(ocf) & set(capex)}
    # A year with revenue or with net income: a revenue series that stops (a tag change GABI cannot
    # bridge safely) leaves explained gaps instead of showing only old years.
    ends = sorted(revenue)
    for end in sorted(net_income):
        if _at_anchor(dict.fromkeys(ends, end), end, tolerance_days=ALIGNMENT_TOLERANCE_DAYS) is None:
            ends.append(end)
    anchors = sorted(ends)[-years:]
    result = []
    for end in anchors:
        found = {name: _at_anchor(series, end, tolerance_days=ALIGNMENT_TOLERANCE_DAYS) if series else None
                 for name, series in (("revenue", revenue), ("net_income", net_income), ("free_cash_flow", fcf))}
        filed = [item[1] for item in found.values() if item and item[1]]
        source = (found["revenue"] or found["net_income"] or (None, None))[1]
        result.append({
            "fiscal_year_end": end, "label": label(end), "filed": max(filed) if filed else None,
            "restated": _restated(facts, source),
            **{name: item[0] if item else None for name, item in found.items()},
            "missing": {name: MISSING[name] for name, item in found.items() if item is None},
        })
    return result


def _span(first: dict, last: dict) -> int:
    return round((date.fromisoformat(last["fiscal_year_end"]) - date.fromisoformat(first["fiscal_year_end"])).days / 365.25)


def reading(points: list[dict], *, has_facts: bool) -> dict:
    """Plain sentences for «¿el negocio crece?»; every number of the text is also in `values`."""
    values: dict = {"years": len(points)}
    if not points:
        text = ("Sin datos: sus informes anuales no traen ingresos ni beneficio en dólares."
                if has_facts else
                "Sin datos: todavía no se han descargado sus informes de la SEC en tu equipo.")
        return {"text": text, "values": values}
    sentences = []
    old = [point["label"] for point in points if point.get("restated")]
    if old:
        values["restated"] = old
    sales = [point for point in points if point["revenue"] is not None and not point.get("restated")]
    if len(sales) >= 2:
        first, last = sales[0], sales[-1]
        span = _span(first, last)
        values["revenue"] = {"first": first["revenue"], "last": last["revenue"], "years": span}
        verb = ("han crecido" if last["revenue"] > first["revenue"] else
                "han bajado" if last["revenue"] < first["revenue"] else "se han mantenido")
        sentence = (f"Sus ingresos {verb} de {money(first['revenue'])} en {first['label']} "
                    f"a {money(last['revenue'])} en {last['label']}")
        if span >= 1 and first["revenue"] > 0 and last["revenue"] > 0:
            growth = (last["revenue"] / first["revenue"]) ** (1 / span) - 1
            if math.isfinite(growth):
                values["revenue"]["per_year"] = growth
                sentence += (f" (un {_percent(abs(growth))} {'más' if growth >= 0 else 'menos'} "
                             "cada año de media)")
        sentences.append(sentence + ".")
    elif sales:
        sentences.append(f"Solo hay un ejercicio con ingresos: {money(sales[0]['revenue'])} en {sales[0]['label']}.")
    elif not any(point["revenue"] is not None for point in points):
        sentences.append("No hay ingresos de estos ejercicios que GABI pueda leer con seguridad.")
    profit = [point for point in points if point["net_income"] is not None]
    if profit:
        losses = [point["label"] for point in profit if point["net_income"] < 0]
        values["net_income"] = {"with_data": len(profit), "losses": losses}
        if not losses:
            sentences.append(f"Ganó dinero en {'el ejercicio' if len(profit) == 1 else f'los {len(profit)} ejercicios'} "
                             "con dato.")
        else:
            sentences.append(f"Tuvo pérdidas en {len(losses)} de {len(profit)} ejercicios ({', '.join(losses)}).")
    cash = [point for point in points if point["free_cash_flow"] is not None]
    if cash:
        positive = sum(point["free_cash_flow"] > 0 for point in cash)
        values["free_cash_flow"] = {"with_data": len(cash), "positive": positive}
        sentences.append(f"Le quedó dinero tras pagar sus inversiones (caja libre positiva) en {positive} de "
                         f"{len(cash)} ejercicios.")
    if old:
        sentences.append(f"La empresa rehízo después sus cifras de {', '.join(old)} (por ejemplo, al vender o "
                         "separar un negocio): se muestran tal como se publicaron, pero no se comparan con las "
                         "más recientes.")
    return {"text": " ".join(sentences), "values": values}
