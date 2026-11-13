"""Compara un filing SEC (10-K/10-Q) con el anterior del mismo tipo, usando
solo las métricas fundamentales que EDGAR ya parsea (edgar.py): ingresos,
márgenes, FCF, deuda, caja y ROIC -- no compara texto (Risk Factors, MD&A,
guidance) todavía, eso queda para una segunda fase explícitamente fuera de
alcance aquí, y en ningún caso depende de un LLM para los números.

"Cambio material" es una regla explícita de GABI (MATERIALITY, con
umbrales configurables), no una conclusión de inversión -- exactamente
igual que composite_score no lo es.

El cálculo anual de EDGAR (edgar.compute_edgar_metrics) no sirve para comparar
10-Q con 10-Q; ``period_metrics`` es una extracción paralela por accession que no
toca ese cálculo validado. Sin red ni base de datos: recibe los hechos ya cargados."""
from datetime import date

import pandas as pd

FORM_DURATION_RANGES = {"10-K": (340, 380), "10-Q": (75, 105)}
FORM_FP_VALUES = {"10-K": ("FY",), "10-Q": ("Q1", "Q2", "Q3")}

# Métrica -> cómo se mide el cambio ("pct": relativo; "abs_pp": puntos
# porcentuales absolutos, para ratios que ya son un %) y a partir de qué
# magnitud se considera material. higher_is_better decide si un cambio es
# mejora o deterioro, no si es material -- eso lo decide solo el umbral.
MATERIALITY = {
    "revenue": {"higher_is_better": True, "kind": "pct", "threshold": 0.10},
    "operating_margin": {"higher_is_better": True, "kind": "abs_pp", "threshold": 0.05},
    "gross_margin": {"higher_is_better": True, "kind": "abs_pp", "threshold": 0.05},
    "fcf": {"higher_is_better": True, "kind": "pct", "threshold": 0.20},
    "debt": {"higher_is_better": False, "kind": "pct", "threshold": 0.15},
    "cash": {"higher_is_better": True, "kind": "pct", "threshold": 0.20},
    "roic": {"higher_is_better": True, "kind": "abs_pp", "threshold": 0.03},
}


def filing_index_url(cik: str, accn: str) -> str:
    """Página índice del filing en EDGAR -- válida para cualquier accession,
    a diferencia de enlazar al documento primario (que exige saber su
    nombre de archivo exacto, no derivable de edgar_facts)."""
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn.replace('-', '')}/{accn}-index.htm"


def filings_from_facts(df: pd.DataFrame, form: str, cik: str | None = None) -> pd.DataFrame:
    """Índice de filings de un tipo a partir de hechos ya cargados (una fila por accession)."""
    if form not in FORM_DURATION_RANGES:
        raise ValueError(f"form debe ser uno de {list(FORM_DURATION_RANGES)}")
    cols = ["accn", "form", "filed_date", "period_end", "url"]
    if df.empty:
        return pd.DataFrame(columns=cols)
    df = df[(df["form"] == form) & df["accn"].notna() & df["filed_date"].notna()]
    if df.empty:
        return pd.DataFrame(columns=cols)
    grouped = df.groupby("accn").agg(filed_date=("filed_date", "max"), period_end=("end_date", "max")).reset_index()
    grouped["form"] = form
    grouped["url"] = grouped["accn"].map(lambda a: filing_index_url(cik, a)) if cik else None
    grouped = grouped.sort_values("filed_date").reset_index(drop=True)
    return grouped[cols]


def period_metrics(facts: pd.DataFrame, accn: str, form: str, tags: dict[str, list[str]]) -> dict:
    """Métricas fundamentales reportadas ESPECÍFICAMENTE en el filing
    `accn` -- no "todo lo conocido hasta esa fecha" (eso ya lo hace
    edgar.compute_edgar_metrics_as_of para 10-K), sino solo el periodo
    propio de ese filing concreto (su ejercicio anual si es 10-K, su
    trimestre si es 10-Q). Al filtrar por accn, la comparación resultante
    es entre dos periodos DISTINTOS y no solapados (el filing actual es
    cronológicamente posterior al anterior) -- información nueva, no una
    reformulación del mismo periodo.

    ``tags``: etiquetas XBRL por concepto (revenue, operating_income, gross_profit,
    ocf, capex, net_income, equity, debt, cash), las mismas que usa EDGAR en GABI."""
    df = facts
    if df.empty:
        return {}
    df = df[df["accn"] == accn]
    if df.empty:
        return {}
    min_days, max_days = FORM_DURATION_RANGES[form]
    fp_values = FORM_FP_VALUES[form]

    def _duration_days(row):
        try:
            return (date.fromisoformat(row.end_date) - date.fromisoformat(row.start_date)).days
        except (TypeError, ValueError):
            return None

    def _latest_duration(tags):
        candidates = df[df["tag"].isin(tags) & (df["unit"] == "USD") & df["fp"].isin(fp_values)]
        best = None
        for row in candidates.itertuples():
            days = _duration_days(row)
            if days is not None and min_days <= days <= max_days and (best is None or row.end_date > best.end_date):
                best = row
        return float(best.val) if best is not None else None

    def _latest_instant(tags):
        candidates = df[df["tag"].isin(tags) & (df["unit"] == "USD") & df["fp"].isin(fp_values)]
        best = None
        for row in candidates.itertuples():
            if best is None or row.end_date > best.end_date:
                best = row
        return float(best.val) if best is not None else None

    revenue = _latest_duration(tags["revenue"])
    operating_income = _latest_duration(tags["operating_income"])
    gross_profit = _latest_duration(tags["gross_profit"])
    ocf = _latest_duration(tags["ocf"])
    capex = _latest_duration(tags["capex"])
    net_income = _latest_duration(tags["net_income"])
    equity = _latest_instant(tags["equity"])
    debt = _latest_instant(tags["debt"])
    cash = _latest_instant(tags["cash"])

    fcf = (ocf - abs(capex)) if ocf is not None and capex is not None else None
    operating_margin = (operating_income / revenue) if operating_income is not None and revenue else None
    gross_margin = (gross_profit / revenue) if gross_profit is not None and revenue else None
    roic = None
    if net_income is not None and equity is not None and debt is not None and (equity + debt) > 0:
        roic = net_income / (equity + debt)

    return {"revenue": revenue, "operating_margin": operating_margin, "gross_margin": gross_margin,
            "fcf": fcf, "debt": debt, "cash": cash, "roic": roic}


def compare_filing_metrics(previous: dict, current: dict, thresholds: dict = None) -> list[dict]:
    """Función pura: compara dos dicts de métricas (claves de MATERIALITY)
    y devuelve una fila por métrica presente en AMBOS -- sin red, sin base
    de datos, determinista. `direction`: "improvement"/"deterioration" si
    supera el umbral (según higher_is_better), "stable" si no."""
    thresholds = thresholds or {}
    rows = []
    for metric, rule in MATERIALITY.items():
        prev_v, curr_v = previous.get(metric), current.get(metric)
        if prev_v is None or curr_v is None:
            continue
        abs_change = curr_v - prev_v
        pct_change = (abs_change / abs(prev_v)) if prev_v != 0 else None
        threshold = thresholds.get(metric, rule["threshold"])
        magnitude = abs(pct_change) if rule["kind"] == "pct" and pct_change is not None else abs(abs_change)
        if magnitude >= threshold:
            severity = "MATERIAL"
            direction = "improvement" if (abs_change > 0) == rule["higher_is_better"] else "deterioration"
        else:
            severity, direction = "INFO", "stable"
        rows.append({
            "metric": metric, "previous_value": prev_v, "current_value": curr_v,
            "abs_change": abs_change, "pct_change": pct_change,
            "severity": severity, "direction": direction,
        })
    return sorted(rows, key=lambda r: r["metric"])


def material_events(result: dict) -> list[dict]:
    """Convierte las filas MATERIAL de una comparación en eventos con la misma
    forma que ``domain.market.signals.compare_snapshots``, para guardarlos junto
    a los de señales sin que esa regla tenga que conocer los filings."""
    if not result.get("current") or not result.get("previous"):
        return []
    symbol, form = result["symbol"], result["form"]
    curr_date, prev_date = result["current"]["filed_date"], result["previous"]["filed_date"]
    events = []
    for r in result["rows"]:
        if r["severity"] != "MATERIAL":
            continue
        pct = f" ({r['pct_change']:+.1%})" if r["pct_change"] is not None else ""
        events.append({
            "symbol": symbol, "event_type": f"filing_{r['metric']}_{r['direction']}", "severity": "MATERIAL",
            "previous_value": r["previous_value"], "new_value": r["current_value"],
            "cause": f"{form} {curr_date} vs {prev_date}: {r['metric']} {r['direction']}{pct}.",
        })
    return events


def compare_cached(symbol: str, facts: pd.DataFrame, cik: str | None, tags: dict[str, list[str]]) -> list[dict]:
    """El filing más reciente frente al anterior del mismo tipo (10-K y 10-Q), sobre hechos ya cargados."""
    results: list[dict] = []
    for form in ("10-K", "10-Q"):
        filings = filings_from_facts(facts, form, cik)
        if len(filings) < 2:
            results.append({"symbol": symbol, "form": form, "current": None, "previous": None,
                            "rows": [], "events": [], "reason": "Sin dos filings comparables."})
            continue
        current, previous = filings.iloc[-1], filings.iloc[-2]
        current_metrics = period_metrics(facts, str(current["accn"]), form, tags)
        previous_metrics = period_metrics(facts, str(previous["accn"]), form, tags)
        rows = compare_filing_metrics(previous_metrics, current_metrics)
        result = {"symbol": symbol, "form": form, "current": current.to_dict(),
                  "previous": previous.to_dict(), "rows": rows,
                  "reason": None if rows else "Sin metricas comparables entre ambos filings."}
        result["events"] = material_events(result)
        results.append(result)
    return results
