"""Compara un filing SEC (10-K/10-Q) con el anterior del mismo tipo, usando
solo las métricas fundamentales que EDGAR ya parsea (edgar.py): ingresos,
márgenes, FCF, deuda, caja y ROIC -- no compara texto (Risk Factors, MD&A,
guidance) todavía, eso queda para una segunda fase explícitamente fuera de
alcance aquí, y en ningún caso depende de un LLM para los números.

"Cambio material" es una regla explícita de GABI (MATERIALITY, con
umbrales configurables), no una conclusión de inversión -- exactamente
igual que composite_score no lo es.

El pipeline existente de edgar.compute_edgar_metrics() es solo anual
(form='10-K', fp='FY') -- no sirve para comparar 10-Q vs 10-Q. Este módulo
añade una extracción paralela (_period_metrics_for_accn) que no toca ni
generaliza esa función existente, precisamente para no arriesgar el cálculo
ya validado que usa screener/backtest -- es aditivo, no un refactor."""
from datetime import UTC, date, datetime

import pandas as pd

from . import edgar, storage

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

SCHEMA = """
CREATE TABLE IF NOT EXISTS filing_metadata (
    symbol TEXT NOT NULL, form TEXT NOT NULL, accn TEXT NOT NULL,
    filed_date TEXT NOT NULL, period_end TEXT, url TEXT,
    PRIMARY KEY (symbol, form, accn)
);
CREATE TABLE IF NOT EXISTS filing_comparisons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL, form TEXT NOT NULL,
    current_accn TEXT NOT NULL, previous_accn TEXT NOT NULL,
    compared_at TEXT NOT NULL, metric TEXT NOT NULL,
    previous_value REAL, current_value REAL, abs_change REAL, pct_change REAL,
    severity TEXT NOT NULL, direction TEXT NOT NULL,
    UNIQUE (symbol, form, current_accn, previous_accn, metric)
);
"""


def _stored_cik(symbol: str) -> str | None:
    with storage.get_connection() as conn:
        conn.executescript(edgar.SCHEMA)
        row = conn.execute("SELECT cik FROM edgar_metrics WHERE symbol=?", (symbol,)).fetchone()
    return row[0] if row and row[0] else None


def _filing_index_url(cik: str, accn: str) -> str:
    """Página índice del filing en EDGAR -- válida para cualquier accession,
    a diferencia de enlazar al documento primario (que exige saber su
    nombre de archivo exacto, no derivable de edgar_facts)."""
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn.replace('-', '')}/{accn}-index.htm"


def list_filings(symbol: str, form: str, *, entity_id: str | None = None) -> pd.DataFrame:
    """Filings de tipo `form` ('10-K'/'10-Q') para `symbol`, derivados de
    edgar_facts ya descargado -- sin red, y sin duplicar el fetch: cada fila
    es una presentación real (accn), no un hecho individual. Se persisten
    de paso en filing_metadata (accession/fecha de presentación/fin de
    periodo/URL/tipo), como pide el objetivo, aunque se puedan re-derivar
    en cualquier momento a partir de edgar_facts."""
    if form not in FORM_DURATION_RANGES:
        raise ValueError(f"form debe ser uno de {list(FORM_DURATION_RANGES)}")
    cols = ["accn", "form", "filed_date", "period_end", "url"]
    df = edgar.get_edgar_facts(symbol, entity_id=entity_id)
    if df.empty:
        return pd.DataFrame(columns=cols)
    df = df[(df["form"] == form) & df["accn"].notna() & df["filed_date"].notna()]
    if df.empty:
        return pd.DataFrame(columns=cols)
    grouped = df.groupby("accn").agg(filed_date=("filed_date", "max"), period_end=("end_date", "max")).reset_index()
    grouped["form"] = form
    cik = _stored_cik(symbol)
    grouped["url"] = grouped["accn"].map(lambda a: _filing_index_url(cik, a)) if cik else None
    grouped = grouped.sort_values("filed_date").reset_index(drop=True)

    with storage.get_connection() as conn:
        conn.executescript(SCHEMA)
        conn.executemany(
            "INSERT OR REPLACE INTO filing_metadata (symbol, form, accn, filed_date, period_end, url) "
            "VALUES (?,?,?,?,?,?)",
            [(symbol, form, r.accn, r.filed_date, r.period_end, r.url) for r in grouped.itertuples()],
        )
        conn.commit()
    return grouped[cols]


def latest_two_filings(symbol: str, form: str, *, entity_id: str | None = None):
    """(actual, anterior) -- filas (pd.Series) de list_filings, o None
    donde no haya suficiente historial. "Actual" es el más reciente por
    filed_date; si solo hay uno, "anterior" es None (sin comparable
    todavía, no es un error)."""
    filings = list_filings(symbol, form, entity_id=entity_id)
    if filings.empty:
        return None, None
    current = filings.iloc[-1]
    previous = filings.iloc[-2] if len(filings) >= 2 else None
    return current, previous


def _period_metrics_for_accn(symbol: str, accn: str, form: str, *, entity_id: str | None = None) -> dict:
    """Métricas fundamentales reportadas ESPECÍFICAMENTE en el filing
    `accn` -- no "todo lo conocido hasta esa fecha" (eso ya lo hace
    edgar.compute_edgar_metrics_as_of para 10-K), sino solo el periodo
    propio de ese filing concreto (su ejercicio anual si es 10-K, su
    trimestre si es 10-Q). Al filtrar por accn, la comparación resultante
    es entre dos periodos DISTINTOS y no solapados (el filing actual es
    cronológicamente posterior al anterior) -- información nueva, no una
    reformulación del mismo periodo."""
    df = edgar.get_edgar_facts(symbol, entity_id=entity_id)
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

    revenue = _latest_duration(edgar.REVENUE_TAGS)
    operating_income = _latest_duration(edgar.OPERATING_INCOME_TAGS)
    gross_profit = _latest_duration(edgar.GROSS_PROFIT_TAGS)
    ocf = _latest_duration(edgar.OCF_TAGS)
    capex = _latest_duration(edgar.CAPEX_TAGS)
    net_income = _latest_duration(edgar.NET_INCOME_TAGS)
    equity = _latest_instant(edgar.EQUITY_TAGS)
    debt = _latest_instant(edgar.LT_DEBT_TAGS)
    cash = _latest_instant(edgar.CASH_TAGS)

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


def compare_filings(symbol: str, form: str, *, thresholds: dict = None, entity_id: str | None = None) -> dict:
    """Orquesta: identifica el filing actual y el anterior comparable del
    mismo tipo, calcula las métricas propias de cada uno (cada una usa solo
    los hechos con ese accn concreto -- fechados por construcción, nunca
    después del propio filed_date del filing) y las compara. `reason`
    explica por qué no hay comparación posible en vez de fallar (sin
    ningún filing todavía, o solo uno sin comparable anterior)."""
    current, previous = latest_two_filings(symbol, form, entity_id=entity_id)
    if current is None:
        return {"symbol": symbol, "form": form, "rows": [], "current": None, "previous": None,
                "reason": f"No hay ningún filing {form} descargado para {symbol}."}
    if previous is None:
        return {"symbol": symbol, "form": form, "rows": [], "current": current.to_dict(), "previous": None,
                "reason": f"Solo hay un filing {form} -- todavía no hay comparable anterior."}
    current_metrics = _period_metrics_for_accn(symbol, current["accn"], form, entity_id=entity_id)
    previous_metrics = _period_metrics_for_accn(symbol, previous["accn"], form, entity_id=entity_id)
    rows = compare_filing_metrics(previous_metrics, current_metrics, thresholds)
    reason = None if rows else "Sin métricas comparables entre ambos filings (datos insuficientes)."
    return {"symbol": symbol, "form": form, "rows": rows,
            "current": current.to_dict(), "previous": previous.to_dict(), "reason": reason}


def record_comparison(result: dict):
    """Persiste las filas de compare_filings() -- idempotente por el
    UNIQUE de filing_comparisons, igual que signal_monitor.record_events."""
    if not result.get("rows") or not result.get("current") or not result.get("previous"):
        return
    compared_at = datetime.now(UTC).isoformat()
    symbol, form = result["symbol"], result["form"]
    current_accn, previous_accn = result["current"]["accn"], result["previous"]["accn"]
    with storage.get_connection() as conn:
        conn.executescript(SCHEMA)
        conn.executemany(
            "INSERT OR IGNORE INTO filing_comparisons (symbol, form, current_accn, previous_accn, compared_at, "
            "metric, previous_value, current_value, abs_change, pct_change, severity, direction) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            [(symbol, form, current_accn, previous_accn, compared_at, r["metric"], r["previous_value"],
              r["current_value"], r["abs_change"], r["pct_change"], r["severity"], r["direction"])
             for r in result["rows"]],
        )
        conn.commit()


def material_events_for_signal_monitor(result: dict) -> list[dict]:
    """Convierte las filas MATERIAL de un compare_filings() en eventos con
    la misma forma que produce signal_monitor.compare_snapshots, para que
    se puedan persistir con signal_monitor.record_events sin que ese
    módulo tenga que conocer filing_tracker (desacoplado a propósito)."""
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
