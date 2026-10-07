"""Pure SEC XBRL interpretation; facts and fiscal alignment are explicit inputs."""

from datetime import date

REVENUE_TAGS = [
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
]

NET_INCOME_TAGS = ["NetIncomeLoss"]

OCF_TAGS = [
    "NetCashProvidedByUsedInOperatingActivities",
    "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
]

CAPEX_TAGS = ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsForCapitalImprovements"]

EQUITY_TAGS = ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"]

LT_DEBT_TAGS = ["LongTermDebtNoncurrent", "LongTermDebt"]

GROSS_PROFIT_TAGS = ["GrossProfit"]

OPERATING_INCOME_TAGS = ["OperatingIncomeLoss"]

DEPRECIATION_TAGS = [
    "DepreciationDepletionAndAmortization", "DepreciationAmortizationAndAccretionNet", "DepreciationAndAmortization",
]

CASH_TAGS = [
    "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents", "CashAndCashEquivalentsAtCarryingValue",
]

CAPITAL_ALLOCATION_TAGS = [
    "PaymentsForRepurchaseOfCommonStock", "PaymentsForRepurchaseOfCommonAndPreferredStock",
    "ProceedsFromStockOptionsExercised", "ProceedsFromStockIssuedUnderIncentiveAndStockOptionPlans",
    "ProceedsFromIssuanceOfCommonStock", "PaymentsToAcquireBusinessesNetOfCashAcquired",
    "PaymentsToAcquireBusinesses", "PaymentsToAcquireInterestInSubsidiariesAndAffiliates",
]

SHARES_TAGS = ["CommonStockSharesOutstanding", "EntityCommonStockSharesOutstanding"]

TRACKED_TAGS = (
    REVENUE_TAGS + NET_INCOME_TAGS + OCF_TAGS + CAPEX_TAGS + EQUITY_TAGS + LT_DEBT_TAGS
    + GROSS_PROFIT_TAGS + OPERATING_INCOME_TAGS + DEPRECIATION_TAGS + CASH_TAGS
    + CAPITAL_ALLOCATION_TAGS
)

def _extract_annual_values(facts: dict, tag_candidates: list, unit: str = "USD") -> list:
    """[(fecha_fin_ejercicio, valor), ...] ordenado ascendente, solo periodos
    anuales completos (340-380 días) declarados en un 10-K. Se descartan
    trimestres que aparecen mezclados con el mismo form='10-K'/fp='FY' porque
    muchos filings incluyen desgloses trimestrales de contexto."""
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    merged: dict[str, float] = {}
    for tag in tag_candidates:
        node = us_gaap.get(tag)
        if not node:
            continue
        entries = node.get("units", {}).get(unit)
        if not entries:
            continue
        by_end: dict[str, tuple[str, str, float]] = {}
        conflicts: set[str] = set()
        for e in entries:
            if e.get("form") not in {"10-K", "10-K/A"} or e.get("fp") != "FY":
                continue
            start, end, val = e.get("start"), e.get("end"), e.get("val")
            if not start or not end or val is None:
                continue
            try:
                duration_days = (date.fromisoformat(end) - date.fromisoformat(start)).days
            except ValueError:
                continue
            if 340 <= duration_days <= 380:
                candidate = (str(e.get("filed") or ""), str(e.get("accn") or ""), float(val))
                previous = by_end.get(end)
                if previous and previous[:2] == candidate[:2] and previous[2] != candidate[2]:
                    conflicts.add(end)
                elif previous is None or candidate[:2] > previous[:2]:
                    by_end[end] = candidate
        values = {end: row[2] for end, row in by_end.items() if end not in conflicts}
        if not values:
            continue
        if not merged:
            merged.update(values)
            continue
        overlap = set(merged) & set(values)
        # These tags are candidates, not interchangeable by name alone. Only
        # bridge a taxonomy change when at least one same-year USD value
        # reconciles and none of the overlapping values disagree materially.
        if (overlap and all(abs(merged[day] - values[day]) <=
                            0.01 * max(abs(merged[day]), abs(values[day]), 1.0)
                            for day in overlap)):
            for day, value in values.items():
                merged.setdefault(day, value)
    return sorted(merged.items())

def _extract_instant_values(facts: dict, tag_candidates: list, unit: str = "USD") -> list:
    """[(fecha, valor), ...] para partidas de balance ('instant': solo tienen
    fecha de corte, no start/end como los ingresos, que son de 'duration')."""
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    for tag in tag_candidates:
        node = us_gaap.get(tag)
        if not node:
            continue
        entries = node.get("units", {}).get(unit)
        if not entries:
            continue
        by_end: dict[str, tuple[str, str, float]] = {}
        for e in entries:
            if e.get("form") not in {"10-K", "10-K/A"} or e.get("fp") != "FY":
                continue
            end, val = e.get("end"), e.get("val")
            if not end or val is None:
                continue
            # The same balance date appears as current year and as a later
            # comparative: keep the latest filing (as the annual extractor
            # does), independently of row order.
            candidate = (str(e.get("filed") or ""), str(e.get("accn") or ""), val)
            if end not in by_end or candidate[:2] >= by_end[end][:2]:
                by_end[end] = candidate
        if by_end:
            return sorted((end, row[2]) for end, row in by_end.items())
    return []

def _extract_raw_facts(facts: dict, tags: list, unit: str = "USD") -> list:
    """Todas las observaciones (sin filtrar por form/fp/duración) de cada tag
    en `tags`, tal y como las devuelve la API de companyfacts. A diferencia
    de _extract_annual_values/_extract_instant_values, no descarta nada: ni
    trimestres, ni restataciones posteriores del mismo periodo — eso se
    decide al consultar, no al guardar.

    Busca cada tag tanto en la taxonomía us-gaap como en dei (portada del
    informe): el nº de acciones en circulación, por ejemplo, a veces solo
    se etiqueta en dei, no en us-gaap (comprobado con datos reales)."""
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    dei = facts.get("facts", {}).get("dei", {})
    rows = []
    for tag in tags:
        node = us_gaap.get(tag) or dei.get(tag)
        if not node:
            continue
        entries = node.get("units", {}).get(unit, [])
        for e in entries:
            end, val, accn = e.get("end"), e.get("val"), e.get("accn")
            if not end or val is None or not accn:
                continue
            rows.append({
                "tag": tag, "unit": unit,
                # '' (no NULL) para partidas 'instant' (balance) sin start_date: forma
                # parte de la clave primaria, y dos entradas con distinto periodo
                # (ej. un trimestre vs. un acumulado de 9 meses) que terminan el
                # mismo día y vienen del mismo filing SÍ son observaciones distintas.
                "start_date": e.get("start") or "", "end_date": end, "val": val,
                "form": e.get("form"), "fp": e.get("fp"), "fy": e.get("fy"),
                "filed_date": e.get("filed"), "accn": accn,
            })
    return rows

def _cagr_from_series(series: list, years: int = 3):
    if len(series) < years + 1:
        return None
    dates = [_annual_date(end) for end, _ in series[-years - 1:]]
    if any(not 340 <= (right - left).days <= 380 for left, right in zip(dates, dates[1:])):
        return None
    _, v_now = series[-1]
    _, v_then = series[-1 - years]
    if not v_then or v_then <= 0 or not v_now or v_now <= 0:
        return None
    return (v_now / v_then) ** (1 / years) - 1

def _annual_date(value: str) -> date:
    # Keep the pre-existing year-only helper input used by callers/tests;
    # stored SEC periods always have exact ISO dates.
    return date(int(value), 12, 31) if len(value) == 4 else date.fromisoformat(value)

def _yoy_growth(series: dict):
    """series: {fecha_fin: valor}. Crecimiento del último ejercicio anual
    completo frente al anterior."""
    dates = sorted(series)
    if len(dates) < 2:
        return None
    if not 340 <= (_annual_date(dates[-1]) - _annual_date(dates[-2])).days <= 380:
        return None
    prev, last = series[dates[-2]], series[dates[-1]]
    if not prev or prev <= 0:
        return None
    return (last / prev) - 1

ALIGNMENT_TOLERANCE_DAYS = 45

def _anchor(revenue_series: dict, ni_series: dict) -> str | None:
    if revenue_series:
        return max(revenue_series)
    return max(ni_series) if ni_series else None

def _at_anchor(series: dict, anchor: str, *, tolerance_days: int = ALIGNMENT_TOLERANCE_DAYS):
    """Value of ``series`` for the anchor fiscal year, or None."""
    day = _annual_date(anchor)
    close = [(abs((_annual_date(end) - day).days), end) for end in series
             if abs((_annual_date(end) - day).days) <= tolerance_days]
    return series[min(close)[1]] if close else None

def compute_edgar_metrics(facts: dict, *, fiscal_alignment: bool = False,
                          tolerance_days: int = ALIGNMENT_TOLERANCE_DAYS) -> dict:
    """Métricas EDGAR a partir de una estructura de 'company facts' (la que
    devuelve fetch_company_facts, o la reconstruida por _facts_dict_from_stored
    para una fecha concreta vía compute_edgar_metrics_as_of).

    Devuelve tanto los derivados ya existentes (roic, CAGRs) como los valores
    anuales más recientes en bruto y algunos derivados clásicos adicionales
    (márgenes, EBITDA, deuda neta/EBITDA) — necesarios para reconstruir
    múltiplos (PER, P/VC, P/Ventas, EV/EBITDA) combinándolos con precio y nº
    de acciones de la misma fecha, en screener_asof.py."""
    revenue_series = dict(_extract_annual_values(facts, REVENUE_TAGS))
    ni_series = dict(_extract_annual_values(facts, NET_INCOME_TAGS))
    ocf_series = dict(_extract_annual_values(facts, OCF_TAGS))
    capex_series = dict(_extract_annual_values(facts, CAPEX_TAGS))
    equity_series = dict(_extract_instant_values(facts, EQUITY_TAGS))
    debt_series = dict(_extract_instant_values(facts, LT_DEBT_TAGS))
    gross_profit_series = dict(_extract_annual_values(facts, GROSS_PROFIT_TAGS))
    operating_income_series = dict(_extract_annual_values(facts, OPERATING_INCOME_TAGS))
    da_series = dict(_extract_annual_values(facts, DEPRECIATION_TAGS))
    cash_series = dict(_extract_instant_values(facts, CASH_TAGS))

    fcf_series = dict(sorted(
        (d, ocf_series[d] - abs(capex_series[d]))
        for d in (set(ocf_series) & set(capex_series))
    ))

    anchor = _anchor(revenue_series, ni_series) if fiscal_alignment else None
    stale: list[str] = []

    roic = None
    common_dates = sorted(set(ni_series) & set(equity_series) & set(debt_series))
    latest_roic_date = common_dates[-1] if common_dates else None
    if anchor:
        latest_roic_date = None
        parts = [_at_anchor(series, anchor, tolerance_days=tolerance_days) for series in (ni_series, equity_series, debt_series)]
        if all(part is not None for part in parts) and parts[1] + parts[2] > 0:
            roic = parts[0] / (parts[1] + parts[2])
    if latest_roic_date:
        # Aproximación: NOPAT ~ NetIncomeLoss (sin ajuste fiscal) sobre
        # capital invertido ~ patrimonio neto + deuda a largo plazo.
        invested_capital = equity_series[latest_roic_date] + debt_series[latest_roic_date]
        if invested_capital > 0:
            roic = ni_series[latest_roic_date] / invested_capital

    def _latest(series, name=None):
        if not series:
            return None
        if anchor is None:
            return series[max(series)]
        value = _at_anchor(series, anchor, tolerance_days=tolerance_days)
        if value is None and name:
            stale.append(name)
        return value

    latest_revenue = _latest(revenue_series, "revenue")
    latest_ni = _latest(ni_series, "net_income")
    latest_equity = _latest(equity_series, "equity")
    latest_debt = _latest(debt_series, "debt")
    latest_cash = _latest(cash_series, "cash")
    latest_gross_profit = _latest(gross_profit_series, "gross_profit")
    latest_operating_income = _latest(operating_income_series, "operating_income")
    latest_da = _latest(da_series, "depreciation")
    latest_fcf = _latest(fcf_series, "fcf")

    gross_margin = (latest_gross_profit / latest_revenue) if latest_gross_profit and latest_revenue else None
    operating_margin = (latest_operating_income / latest_revenue) if latest_operating_income and latest_revenue else None
    profit_margin = (latest_ni / latest_revenue) if latest_ni is not None and latest_revenue else None

    ebitda = None
    if latest_operating_income is not None and latest_da is not None:
        ebitda = latest_operating_income + latest_da
    net_debt = None
    if latest_debt is not None and "cash" not in stale:
        net_debt = latest_debt - (latest_cash or 0)
    net_debt_to_ebitda = (net_debt / ebitda) if net_debt is not None and ebitda else None
    fcf_cagr = _cagr_from_series(sorted(fcf_series.items()), 3) if "fcf" not in stale else None
    earnings_growth = _yoy_growth(ni_series) if "net_income" not in stale else None

    return {
        # Derivados ya existentes (usados hoy en el screener "en vivo").
        "revenue_cagr_3y": _cagr_from_series(sorted(revenue_series.items()), 3),
        "fcf_cagr_3y": fcf_cagr,
        "roic": roic,
        # Valores anuales más recientes en bruto — base para reconstruir
        # múltiplos combinándolos con precio y nº de acciones de una fecha.
        "latest_revenue": latest_revenue,
        "latest_net_income": latest_ni,
        "latest_equity": latest_equity,
        "latest_debt": latest_debt,
        "latest_cash": latest_cash,
        "latest_fcf": latest_fcf,
        "latest_ebitda": ebitda,
        "latest_period_end": max(revenue_series) if revenue_series else None,
        # Derivados clásicos adicionales (márgenes, deuda neta/EBITDA, crecimiento YoY).
        "gross_margin": gross_margin,
        "operating_margin": operating_margin,
        "profit_margin": profit_margin,
        "net_debt_to_ebitda": net_debt_to_ebitda,
        "revenue_growth_yoy": _yoy_growth(revenue_series),
        "earnings_growth_yoy": earnings_growth,
        # #38: components reported for another fiscal year (alignment only).
        "fiscal_anchor": anchor,
        "stale_components": sorted(stale),
    }

def fundamental_missing_reasons(facts: dict, *, fiscal_alignment: bool = False,
                          tolerance_days: int = ALIGNMENT_TOLERANCE_DAYS) -> dict[str, str | None]:
    """Why each SEC-derived Composite input is missing (None = computable).

    Mirrors ``compute_edgar_metrics`` without changing it: same extractors,
    same rules. Market multiples also need price and shares; see
    ``screener_asof.fundamental_diagnostics``.
    """
    revenue = dict(_extract_annual_values(facts, REVENUE_TAGS))
    net_income = dict(_extract_annual_values(facts, NET_INCOME_TAGS))
    ocf = dict(_extract_annual_values(facts, OCF_TAGS))
    capex = dict(_extract_annual_values(facts, CAPEX_TAGS))
    equity = dict(_extract_instant_values(facts, EQUITY_TAGS))
    debt = dict(_extract_instant_values(facts, LT_DEBT_TAGS))
    operating_income = dict(_extract_annual_values(facts, OPERATING_INCOME_TAGS))
    depreciation = dict(_extract_annual_values(facts, DEPRECIATION_TAGS))
    fcf = {day: ocf[day] - abs(capex[day]) for day in set(ocf) & set(capex)}

    def cagr_reason(series: dict, label: str) -> str | None:
        if not series:
            return f"no_annual_{label}"
        values = sorted(series.items())
        if len(values) < 4:
            return f"fewer_than_4_annual_{label}_values"
        if _cagr_from_series(values, 3) is None:
            dates = [_annual_date(end) for end, _ in values[-4:]]
            if any(not 340 <= (right - left).days <= 380 for left, right in zip(dates, dates[1:])):
                return "non_consecutive_fiscal_years"
            return "non_positive_start_or_end_value"
        return None

    anchor = _anchor(revenue, net_income) if fiscal_alignment else None

    def stale(series: dict) -> bool:
        return bool(anchor and series and _at_anchor(series, anchor, tolerance_days=tolerance_days) is None)

    def latest(series: dict):
        return _at_anchor(series, anchor, tolerance_days=tolerance_days) if anchor else series[max(series)]

    roic_reason: str | None
    ebitda_reason: str | None
    common = sorted(set(net_income) & set(equity) & set(debt))
    if anchor and net_income and equity and debt:
        if any(stale(series) for series in (net_income, equity, debt)):
            roic_reason = "stale_component"
        else:
            invested = latest(equity) + latest(debt)
            roic_reason = None if invested > 0 else "non_positive_invested_capital"
    elif common and not anchor:
        invested = equity[common[-1]] + debt[common[-1]]
        roic_reason = None if invested > 0 else "non_positive_invested_capital"
    else:
        roic_reason = ("no_net_income" if not net_income else "no_equity" if not equity else
                       "no_long_term_debt" if not debt else "no_common_fiscal_year_end")
    if not revenue:
        margin_reason = "no_annual_revenue"
    elif not operating_income:
        margin_reason = "no_operating_income"
    elif stale(operating_income):
        margin_reason = "stale_component"
    else:
        margin_reason = None
    if not operating_income:
        ebitda_reason = "no_operating_income"
    elif not depreciation:
        ebitda_reason = "no_depreciation"
    elif stale(operating_income) or stale(depreciation):
        ebitda_reason = "stale_component"
    else:
        ebitda = latest(operating_income) + latest(depreciation)
        ebitda_reason = None if ebitda > 0 else "non_positive_ebitda"
    fcf_reason = cagr_reason(fcf, "fcf") if (ocf and capex) else ("no_operating_cash_flow" if not ocf else "no_capex")
    if fcf_reason is None and stale(fcf):
        fcf_reason = "stale_component"
    return {
        "revenue_cagr_3y": cagr_reason(revenue, "revenue"),
        "fcf_cagr_3y": fcf_reason,
        "roic": roic_reason,
        "operating_margin": margin_reason,
        "net_income": ("no_net_income" if not net_income else "stale_component" if stale(net_income) else None),
        "equity": ("no_equity" if not equity else "stale_component" if stale(equity) else None),
        "ebitda": ebitda_reason,
    }

def extract_latest_filings(submissions: dict) -> dict:
    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accessions = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])
    cik = str(submissions.get("cik", "")).zfill(10)

    result = {}
    for form_wanted, key in (("10-K", "10k"), ("10-Q", "10q")):
        for i, f in enumerate(forms):
            if f == form_wanted and i < len(accessions) and i < len(primary_docs):
                acc_nodash = accessions[i].replace("-", "")
                result[f"latest_{key}_date"] = dates[i] if i < len(dates) else None
                result[f"latest_{key}_url"] = (
                    f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_nodash}/{primary_docs[i]}"
                )
                break
    return result
