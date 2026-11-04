"""Accounting warning signs from structured SEC data, without AI or text (#293). Version ``tenk-flags-v1``.

Every sign has a fixed rule and threshold and says which values and which SEC
filing (accession and date) it used. Only what was filed by the analysis date
counts (point in time). A sign without the data it needs is «no evaluable»,
never «sin alerta». A sign asks the investor to review; it never says to sell.
"""

from datetime import date, timedelta

from gabi.domain.market import checklist, current_reports, sec_facts

VERSION = "tenk-flags-v1"
LOOKBACK_DAYS = 365
# Receivables growing this many points faster than revenue in the latest fiscal year.
RECEIVABLES_GAP = 0.15
# Sloan accrual ratio: (net income − operating cash flow) / average total assets.
ACCRUAL_RATIO = 0.10
# Diluted average shares growing more than this in the latest fiscal year.
DILUTION = 0.05

# The same tags the Composite and the checklist store (sec_facts, checklist); receivables are new.
REVENUE_TAGS = sec_facts.REVENUE_TAGS
RECEIVABLE_TAGS = ["AccountsReceivableNetCurrent"]
NET_INCOME_TAGS = sec_facts.NET_INCOME_TAGS
OCF_TAGS = sec_facts.OCF_TAGS
ASSETS_TAGS = checklist.ASSETS_TAGS
DILUTED_SHARES_TAGS = checklist.DILUTED_SHARES_TAGS
# USD tags only this module reads; the sync stores them (application/market/sec_xbrl.FACT_TAGS).
USD_TAGS = RECEIVABLE_TAGS
FILING_FORMS = ("10-K/A", "NT 10-K")

LABELS = {
    "amended_10k": "Cuentas anuales corregidas (10-K/A)",
    "late_10k": "Informe anual presentado tarde (NT 10-K)",
    "auditor_change": "Cambio de auditor (8-K Item 4.01)",
    "restatement": "Cuentas anteriores que ya no son fiables (8-K Item 4.02)",
    "receivables": "Cuentas a cobrar que crecen más que las ventas",
    "accruals": "Beneficio muy por encima de la caja que genera",
    "dilution": "Más acciones en circulación (dilución)",
}
RULES = {
    "amended_10k": f"Se presentó un 10-K/A en los {LOOKBACK_DAYS} días anteriores.",
    "late_10k": f"Se presentó un NT 10-K en los {LOOKBACK_DAYS} días anteriores.",
    "auditor_change": f"Un 8-K con Item 4.01 en los {LOOKBACK_DAYS} días anteriores.",
    "restatement": f"Un 8-K con Item 4.02 en los {LOOKBACK_DAYS} días anteriores.",
    "receivables": "Crecimiento de las cuentas a cobrar − crecimiento de las ventas, último ejercicio del 10-K.",
    "accruals": "(Beneficio neto − flujo de caja operativo) / activos totales medios, último ejercicio del 10-K.",
    "dilution": "Crecimiento de las acciones diluidas medias, último ejercicio del 10-K.",
}
THRESHOLDS = {"receivables": RECEIVABLES_GAP, "accruals": ACCRUAL_RATIO, "dilution": DILUTION}


def _flag(key: str, status: str, *, values: dict | None = None, source: dict | None = None,
          reason: str | None = None) -> dict:
    return {"key": key, "label": LABELS[key], "status": status, "rule": RULES[key],
            "threshold": THRESHOLDS.get(key), "values": values or {}, "source": source, "reason": reason}


def _annual(facts: dict, tags: list[str], *, unit: str = "USD", instant: bool = False) -> dict[str, dict]:
    """Fiscal year end → the latest-filed 10-K value of the first tag that reports it.

    Flows need a 340–380 day period; balances are the 10-K instants. Each value keeps
    its accession and filing date, so a sign can say where it came from.
    """
    us_gaap = (facts.get("facts") or {}).get("us-gaap") or {}
    result: dict[str, dict] = {}
    for tag in tags:
        for entry in ((us_gaap.get(tag) or {}).get("units") or {}).get(unit) or []:
            if entry.get("form") not in {"10-K", "10-K/A"} or entry.get("val") is None or not entry.get("end"):
                continue
            if not instant:
                if entry.get("fp") != "FY" or not entry.get("start"):
                    continue
                days = (date.fromisoformat(entry["end"]) - date.fromisoformat(entry["start"])).days
                if not 340 <= days <= 380:
                    continue
            elif entry.get("start"):
                continue
            end, current = entry["end"], result.get(entry["end"])
            if current is not None and current["tag"] != tag:
                continue  # The first tag that reports a year keeps it.
            if current is None or (entry.get("filed") or "") >= current["filed"]:
                result[end] = {"value": float(entry["val"]), "filed": entry.get("filed") or "",
                               "accession": entry.get("accn"), "tag": tag}
    return dict(sorted(result.items()))


def _source(row: dict, end: str) -> dict:
    return {"form": "10-K", "accession": row["accession"], "filed_date": row["filed"], "period_end": end}


def _last_two(series: dict[str, dict]) -> tuple[str, dict, str, dict] | None:
    """The latest fiscal year and the one before it, if they are about a year apart."""
    ends = sorted(series)
    if len(ends) < 2:
        return None
    end, prior = ends[-1], ends[-2]
    if not 340 <= (date.fromisoformat(end) - date.fromisoformat(prior)).days <= 380:
        return None
    return end, series[end], prior, series[prior]


def _growth(now: float, before: float) -> float | None:
    return None if before <= 0 else now / before - 1


def receivables(facts: dict) -> dict:
    sales, owed = _annual(facts, REVENUE_TAGS), _annual(facts, RECEIVABLE_TAGS, instant=True)
    pair = _last_two({end: owed[end] for end in owed if end in sales})
    if pair is None:
        return _flag("receivables", "no_evaluable", reason="Faltan las ventas o las cuentas a cobrar de dos "
                                                           "ejercicios seguidos en el 10-K.")
    end, now, prior, before = pair
    owed_growth, sales_growth = _growth(now["value"], before["value"]), _growth(sales[end]["value"],
                                                                                sales[prior]["value"])
    if owed_growth is None or sales_growth is None:
        return _flag("receivables", "no_evaluable", reason="Ventas o cuentas a cobrar del año anterior ≤ 0.")
    gap = owed_growth - sales_growth
    values = {"period_end": end, "previous_period_end": prior, "receivables": now["value"],
              "previous_receivables": before["value"], "revenue": sales[end]["value"],
              "previous_revenue": sales[prior]["value"], "receivables_growth": owed_growth,
              "revenue_growth": sales_growth, "gap": gap}
    return _flag("receivables", "alerta" if gap > RECEIVABLES_GAP else "sin_alerta", values=values,
                 source=_source(now, end))


def accruals(facts: dict) -> dict:
    income, cash, assets = _annual(facts, NET_INCOME_TAGS), _annual(facts, OCF_TAGS), _annual(
        facts, ASSETS_TAGS, instant=True)
    pair = _last_two({end: assets[end] for end in assets})
    if pair is None or pair[0] not in income or pair[0] not in cash:
        return _flag("accruals", "no_evaluable", reason="Faltan el beneficio, el flujo de caja operativo o los "
                                                        "activos de dos cierres seguidos en el 10-K.")
    end, now, prior, before = pair
    average = (now["value"] + before["value"]) / 2
    if average <= 0:
        return _flag("accruals", "no_evaluable", reason="Activos totales medios ≤ 0.")
    ratio = (income[end]["value"] - cash[end]["value"]) / average
    values = {"period_end": end, "net_income": income[end]["value"], "operating_cash_flow": cash[end]["value"],
              "average_assets": average, "ratio": ratio}
    return _flag("accruals", "alerta" if ratio > ACCRUAL_RATIO else "sin_alerta", values=values,
                 source=_source(income[end], end))


def dilution(facts: dict) -> dict:
    pair = _last_two(_annual(facts, DILUTED_SHARES_TAGS, unit="shares"))
    if pair is None:
        return _flag("dilution", "no_evaluable", reason="Faltan las acciones diluidas medias de dos ejercicios "
                                                        "seguidos en el 10-K.")
    end, now, prior, before = pair
    growth = _growth(now["value"], before["value"])
    if growth is None:
        return _flag("dilution", "no_evaluable", reason="Acciones del año anterior ≤ 0.")
    values = {"period_end": end, "shares": now["value"], "previous_shares": before["value"], "growth": growth}
    return _flag("dilution", "alerta" if growth > DILUTION else "sin_alerta", values=values, source=_source(now, end))


def _recent(rows: list[dict], as_of: date) -> list[dict]:
    start = (as_of - timedelta(days=LOOKBACK_DAYS)).isoformat()
    return [row for row in rows if row.get("filed_date") and start <= row["filed_date"] <= as_of.isoformat()]


def filing_flags(index: dict | None, as_of: date) -> list[dict]:
    """10-K/A, NT 10-K and the 8-K Items 4.01/4.02 of the stored SEC index, filed in the last year."""
    keys = ("amended_10k", "late_10k", "auditor_change", "restatement")
    captured = set((index or {}).get("forms") or [])
    if not index or not index.get("captured_at"):
        return [_flag(key, "no_evaluable", reason="No se ha descargado el índice de presentaciones SEC de esta "
                                                  "empresa.") for key in keys]
    rows = _recent(index.get("rows") or [], as_of)
    flags = []
    for key, form in (("amended_10k", "10-K/A"), ("late_10k", "NT 10-K")):
        if form not in captured:
            flags.append(_flag(key, "no_evaluable", reason="El índice guardado es anterior a esta comprobación: "
                                                           "vuelve a descargar los datos SEC."))
            continue
        found = [row for row in rows if row["form"] == form]
        flags.append(_alert_or_clear(key, found, index["captured_at"]))
    for key, item in (("auditor_change", "4.01"), ("restatement", "4.02")):
        found = [row for row in rows if row["form"] in current_reports.FORMS
                 and item in current_reports.parse_items(row.get("items"))]
        flags.append(_alert_or_clear(key, found, index["captured_at"]))
    return flags


def _alert_or_clear(key: str, found: list[dict], captured_at: str) -> dict:
    if not found:
        return _flag(key, "sin_alerta", values={"index_captured_at": captured_at})
    latest = max(found, key=lambda row: (row["filed_date"], row["accession"]))
    return _flag(key, "alerta", values={"filings": len(found), "index_captured_at": captured_at},
                 source={"form": latest["form"], "accession": latest["accession"],
                         "filed_date": latest["filed_date"], "period_end": latest.get("report_date")})


def evaluate(facts: dict, index: dict | None, as_of: date) -> dict:
    """All signs at ``as_of``; ``facts`` and ``index`` must hold only what was filed by then."""
    flags = filing_flags(index, as_of) + [receivables(facts), accruals(facts), dilution(facts)]
    counts = {status: sum(flag["status"] == status for flag in flags)
              for status in ("alerta", "sin_alerta", "no_evaluable")}
    return {"version": VERSION, "as_of": as_of.isoformat(), "flags": flags, "counts": counts}
