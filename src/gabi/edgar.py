"""Datos financieros oficiales de SEC EDGAR (XBRL): gratis, sin API key,
directamente de los 10-K/10-Q presentados por cada empresa.

Se usa para complementar yfinance en tres cosas que con datos gratuitos de
Yahoo son poco fiables o directamente no existen:
  - Crecimiento de ingresos y de flujo de caja libre a 3 años (CAGR), con
    histórico anual real en vez de los ~4-8 trimestres que da yfinance.
  - ROIC aproximado (yfinance no lo expone).
  - Enlaces directos al último 10-K/10-Q, para poder abrir las cuentas reales
    de la empresa (justo lo que recomienda cualquier guía de aprendizaje).
"""
import concurrent.futures as cf
from datetime import UTC, date, datetime

import pandas as pd
import requests

from . import config, storage
from .data_fetch import _classify_error

TICKER_CIK_URL = "https://www.sec.gov/files/company_tickers.json"
COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
CIK_CACHE = config.DATA_DIR / "sec_cik_map.csv"

# Distintas empresas/años usan distintas etiquetas XBRL para el mismo
# concepto (cambios de taxonomía); se prueban en orden hasta encontrar una
# con datos.
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
# 'shares', no 'USD': se extraen y guardan por separado.
# "CommonStockSharesOutstanding" vive en la taxonomía us-gaap; muchas
# empresas (comprobado con Abbott, entre otras) no la usan y solo etiquetan
# el nº de acciones en la portada del informe bajo la taxonomía "dei"
# (EntityCommonStockSharesOutstanding) — _extract_raw_facts mira en ambas.
SHARES_TAGS = ["CommonStockSharesOutstanding", "EntityCommonStockSharesOutstanding"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS edgar_metrics (
    symbol TEXT PRIMARY KEY,
    cik TEXT,
    fetched_at TEXT NOT NULL,
    revenue_cagr_3y REAL,
    fcf_cagr_3y REAL,
    roic REAL,
    latest_10k_date TEXT,
    latest_10k_url TEXT,
    latest_10q_date TEXT,
    latest_10q_url TEXT
);
"""

# Histórico crudo y fechado, sin filtrar ni interpretar (fase "solo datos
# limpios y auditables"): cada fila es un hecho XBRL tal y como se presentó
# ante la SEC, con su propia fecha de presentación (filed_date). Es la base
# necesaria para poder reconstruir más adelante "qué se sabía en una fecha
# concreta" sin sesgo de mirar al futuro (look-ahead bias) — cosa que
# edgar_metrics, al guardar solo el último valor calculado, no permite.
# Se guardan TODAS las observaciones de cada partida (incluidas las que
# aparecen repetidas o revisadas en filings posteriores), no solo la última;
# decidir cuál usar para una fecha dada es trabajo de la capa de consulta
# (fase 2), no de la ingesta.
FACTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS edgar_facts (
    symbol TEXT NOT NULL,
    tag TEXT NOT NULL,
    unit TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    val REAL NOT NULL,
    form TEXT,
    fp TEXT,
    fy INTEGER,
    filed_date TEXT,
    accn TEXT NOT NULL,
    PRIMARY KEY (symbol, tag, unit, start_date, end_date, accn)
);
CREATE INDEX IF NOT EXISTS idx_edgar_facts_symbol_tag ON edgar_facts (symbol, tag);
"""

# Todas las etiquetas en USD que se usan para calcular métricas (ver más
# abajo): es lo que se persiste en bruto en edgar_facts con unit='USD'.
TRACKED_TAGS = (
    REVENUE_TAGS + NET_INCOME_TAGS + OCF_TAGS + CAPEX_TAGS + EQUITY_TAGS + LT_DEBT_TAGS
    + GROSS_PROFIT_TAGS + OPERATING_INCOME_TAGS + DEPRECIATION_TAGS + CASH_TAGS
)


def _headers():
    return {"User-Agent": config.SEC_USER_AGENT}


def get_cik_map(force_refresh: bool = False) -> pd.DataFrame:
    """DataFrame[symbol, cik, title]. cik en formato de 10 dígitos con ceros
    a la izquierda, tal y como lo requieren las URLs de companyfacts/submissions."""
    if not force_refresh and CIK_CACHE.exists():
        return pd.read_csv(CIK_CACHE, dtype={"cik": str})
    resp = requests.get(TICKER_CIK_URL, headers=_headers(), timeout=20)
    resp.raise_for_status()
    data = resp.json()
    rows = [
        {"symbol": v["ticker"], "cik": str(v["cik_str"]).zfill(10), "title": v.get("title", "")}
        for v in data.values()
    ]
    df = pd.DataFrame(rows)
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(CIK_CACHE, index=False)
    return df


# Caché persistente (symbol -> cik, title) de resoluciones que YA han
# funcionado alguna vez. get_cik_map() es el mapeo EN VIVO de la SEC — solo
# tiene tickers actualmente en uso, así que una empresa deslistada hace
# tiempo desaparece de ahí aunque su historial de filings siga existiendo en
# EDGAR. Esta caché evita depender de que el ticker siga vivo para poder
# seguir usando algo que ya se resolvió una vez.
#
# OJO — esto NO arregla el reciclaje de tickers: cuando una empresa
# desaparece, la bolsa puede reasignar su ticker a otra empresa totalmente
# distinta más adelante (comprobado con datos reales: "APC" era Anadarko
# Petroleum en 2019 y hoy en la SEC apunta a "ARKO Petroleum Corp", una
# empresa distinta; "BBT" era BB&T y hoy es "Beacon Financial Corp"). Por
# eso get_cik_for_symbol() siempre devuelve también el 'title' resuelto —
# para que se pueda mostrar en la UI y detectar a simple vista un posible
# reciclaje, en vez de fiarse ciegamente del ticker.
RESOLUTIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS cik_resolutions (
    symbol TEXT PRIMARY KEY,
    cik TEXT NOT NULL,
    title TEXT,
    resolved_at TEXT NOT NULL
);
"""


def _remember_cik_resolution(symbol: str, cik: str, title: str):
    with storage.get_connection() as conn:
        conn.executescript(RESOLUTIONS_SCHEMA)
        conn.execute(
            "INSERT OR REPLACE INTO cik_resolutions (symbol, cik, title, resolved_at) VALUES (?,?,?,?)",
            (symbol, cik, title, datetime.now(UTC).isoformat()),
        )
        conn.commit()


def _get_cached_cik_resolution(symbol: str):
    with storage.get_connection() as conn:
        conn.executescript(RESOLUTIONS_SCHEMA)
        row = conn.execute(
            "SELECT cik, title FROM cik_resolutions WHERE symbol = ?", (symbol,),
        ).fetchone()
    return (row[0], row[1]) if row else (None, None)


def get_resolved_title(symbol: str):
    """Nombre de empresa tal y como lo tiene registrado la SEC para el CIK
    que se resolvió para `symbol` (vivo o de la caché). Pensado para que la
    UI lo muestre junto al ticker — así, si un ticker fue reciclado a otra
    empresa distinta desde entonces, se nota a simple vista."""
    _cik, title = _get_cached_cik_resolution(symbol)
    return title


def get_cik_for_symbol(symbol: str, cik_map: pd.DataFrame = None):
    """(cik, title) para un símbolo: primero prueba el mapeo EN VIVO actual
    de la SEC; si no aparece ahí (típico en empresas ya deslistadas), cae a
    la caché local de resoluciones anteriores. (None, None) si no se puede
    resolver de ninguna forma — deliberadamente NO se intenta adivinar por
    otra vía, porque atribuir por error los datos de una empresa distinta
    que hoy recicla ese ticker sería peor que no tener datos."""
    if cik_map is None:
        cik_map = get_cik_map()
    row = cik_map[cik_map["symbol"] == symbol]
    if row.empty and "." in symbol:
        # Notación de clases de acción: los datasets de composición de índice usan
        # el punto (ej. "BRK.B"), pero el mapeo de la SEC usa guión ("BRK-B") —
        # es la misma acción, no una empresa distinta, así que esta normalización
        # es segura y no entra en conflicto con la política de no adivinar.
        row = cik_map[cik_map["symbol"] == symbol.replace(".", "-")]
    if not row.empty:
        cik, title = row.iloc[0]["cik"], row.iloc[0]["title"]
        _remember_cik_resolution(symbol, cik, title)
        return cik, title
    return _get_cached_cik_resolution(symbol)


def fetch_company_facts(cik: str) -> dict:
    resp = requests.get(COMPANYFACTS_URL.format(cik=cik), headers=_headers(), timeout=30)
    if resp.status_code == 404:
        raise ValueError("SEC EDGAR no tiene datos XBRL estructurados para esta empresa")
    resp.raise_for_status()
    return resp.json()


def fetch_submissions(cik: str) -> dict:
    resp = requests.get(SUBMISSIONS_URL.format(cik=cik), headers=_headers(), timeout=30)
    if resp.status_code == 404:
        raise ValueError("SEC EDGAR no tiene historial de filings para esta empresa")
    resp.raise_for_status()
    return resp.json()


def _extract_annual_values(facts: dict, tag_candidates: list, unit: str = "USD") -> list:
    """[(fecha_fin_ejercicio, valor), ...] ordenado ascendente, solo periodos
    anuales completos (340-380 días) declarados en un 10-K. Se descartan
    trimestres que aparecen mezclados con el mismo form='10-K'/fp='FY' porque
    muchos filings incluyen desgloses trimestrales de contexto."""
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    for tag in tag_candidates:
        node = us_gaap.get(tag)
        if not node:
            continue
        entries = node.get("units", {}).get(unit)
        if not entries:
            continue
        by_end = {}
        for e in entries:
            if e.get("form") != "10-K" or e.get("fp") != "FY":
                continue
            start, end, val = e.get("start"), e.get("end"), e.get("val")
            if not start or not end or val is None:
                continue
            try:
                duration_days = (date.fromisoformat(end) - date.fromisoformat(start)).days
            except ValueError:
                continue
            if 340 <= duration_days <= 380:
                by_end[end] = val
        if by_end:
            return sorted(by_end.items())
    return []


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
        by_end = {}
        for e in entries:
            if e.get("form") != "10-K" or e.get("fp") != "FY":
                continue
            end, val = e.get("end"), e.get("val")
            if not end or val is None:
                continue
            by_end[end] = val
        if by_end:
            return sorted(by_end.items())
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


def upsert_edgar_facts(symbol: str, rows: list):
    if not rows:
        return
    with storage.get_connection() as conn:
        conn.executescript(FACTS_SCHEMA)
        conn.executemany(
            "INSERT OR REPLACE INTO edgar_facts "
            "(symbol, tag, unit, start_date, end_date, val, form, fp, fy, filed_date, accn) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    symbol, r["tag"], r["unit"], r["start_date"], r["end_date"], r["val"],
                    r["form"], r["fp"], r["fy"], r["filed_date"], r["accn"],
                )
                for r in rows
            ],
        )
        conn.commit()


def get_edgar_facts(symbol: str, tags: list = None) -> pd.DataFrame:
    """Histórico crudo y fechado para una empresa. Sin filtrar: incluye
    trimestres, anuales y restataciones. Base para reconstruir 'qué se sabía
    en una fecha concreta' (fase 2), no algo para usar directamente en scoring."""
    query = "SELECT * FROM edgar_facts WHERE symbol = ?"
    params = [symbol]
    if tags:
        placeholders = ",".join("?" * len(tags))
        query += f" AND tag IN ({placeholders})"
        params += list(tags)
    query += " ORDER BY end_date, filed_date"
    with storage.get_connection() as conn:
        conn.executescript(FACTS_SCHEMA)
        return pd.read_sql_query(query, conn, params=params)


def get_last_filed_dates(symbols: list, as_of: str = None) -> dict:
    """{symbol: fecha del filing SEC más reciente que tenemos} para cada
    símbolo (de cualquier tipo: 10-K, 10-Q...). Una empresa viva presenta un
    10-Q como mínimo cada trimestre; si este dato es muy antiguo, casi seguro
    dejó de ser un 'reporting company' (quiebra, exclusión, fusión) — se usa
    como señal para detectar reciclaje de ticker en los precios (ver
    multifactor_backtest._period_returns): si yfinance sigue devolviendo
    cotización reciente bajo ese símbolo mucho después de su último filing,
    lo más probable es que la bolsa haya reasignado el ticker a otra empresa
    distinta, no que la original siga cotizando. En lote (no una consulta por
    símbolo) porque el backtest la llama con el universo completo en cada
    rebalanceo.

    `as_of`: si se pasa, solo cuenta filings con `filed_date <= as_of` —
    imprescindible para que el guard sea point-in-time correcto. Sin esto,
    un ticker reciclado puede colar un filing FUTURO (de la empresa nueva
    que se quedó el símbolo) como si fuera reciente, y el guard nunca
    saltaría — justo el fallo que se pretende detectar. También protege de
    que esos `edgar_facts` de la empresa nueva contaminen el resultado con
    fechas fuera del periodo que se está evaluando."""
    if not symbols:
        return {}
    placeholders = ",".join("?" * len(symbols))
    date_filter = "AND filed_date <= ?" if as_of else ""
    params = list(symbols) + ([as_of] if as_of else [])
    with storage.get_connection() as conn:
        conn.executescript(FACTS_SCHEMA)
        rows = conn.execute(
            f"SELECT symbol, MAX(filed_date) FROM edgar_facts WHERE symbol IN ({placeholders}) "
            f"{date_filter} GROUP BY symbol", params,
        ).fetchall()
    return {symbol: last for symbol, last in rows if last}


def get_value_as_of(symbol: str, tags: list, as_of_date: str, unit: str = "USD"):
    """El valor de un concepto (probando los tags en orden) tal y como se
    conocía en as_of_date — el hecho con el filed_date más reciente que no
    sea posterior a esa fecha, evitando look-ahead bias. None si no había
    ningún dato presentado todavía."""
    df = get_edgar_facts(symbol, tags=tags)
    if df.empty:
        return None
    df = df[(df["unit"] == unit) & (df["filed_date"].notna()) & (df["filed_date"] <= as_of_date)]
    if df.empty:
        return None
    df = df.sort_values(["filed_date", "end_date"])
    return float(df.iloc[-1]["val"])


def get_shares_outstanding_as_of(symbol: str, as_of_date: str):
    """Nº de acciones en circulación conocido en as_of_date (para poder
    calcular capitalización de mercado y múltiplos de una fecha pasada sin
    usar el nº de acciones de HOY, que sería inconsistente con esa fecha)."""
    return get_value_as_of(symbol, SHARES_TAGS, as_of_date, unit="shares")


def _facts_dict_from_stored(symbol: str, as_of_date: str = None) -> dict:
    """Reconstruye una estructura equivalente a la que devuelve
    fetch_company_facts(), pero leída de edgar_facts (ya descargado y
    guardado antes) y, si se pasa as_of_date, recortada a los hechos cuyo
    filed_date no sea posterior a esa fecha. Permite reutilizar
    compute_edgar_metrics() sin red y sin duplicar su lógica, tanto para
    'ahora' como para una fecha pasada — es la pieza central que hace
    posible compute_edgar_metrics_as_of()."""
    df = get_edgar_facts(symbol)
    if df.empty:
        return {"facts": {"us-gaap": {}}}
    if as_of_date:
        df = df[df["filed_date"].notna() & (df["filed_date"] <= as_of_date)]

    us_gaap = {}
    for tag, group in df.groupby("tag"):
        by_unit = {}
        for unit, ug in group.groupby("unit"):
            entries = [
                {
                    "start": (r.start_date or None), "end": r.end_date, "val": r.val,
                    "form": r.form, "fp": r.fp, "fy": r.fy, "filed": r.filed_date, "accn": r.accn,
                }
                for r in ug.itertuples()
            ]
            by_unit[unit] = entries
        us_gaap[tag] = {"units": by_unit}
    return {"facts": {"us-gaap": us_gaap}}


def compute_edgar_metrics_as_of(symbol: str, as_of_date: str) -> dict:
    """compute_edgar_metrics(), pero solo con lo que se conocía públicamente
    en as_of_date (sin red: usa edgar_facts, que debe haberse descargado
    antes desde ⚙️ Configuración). Es la reconstrucción fundamental point-in-
    time — la pieza que evita el look-ahead bias en el ranking histórico."""
    facts = _facts_dict_from_stored(symbol, as_of_date=as_of_date)
    return compute_edgar_metrics(facts)


def _cagr_from_series(series: list, years: int = 3):
    if len(series) < years + 1:
        return None
    _, v_now = series[-1]
    _, v_then = series[-1 - years]
    if not v_then or v_then <= 0 or not v_now or v_now <= 0:
        return None
    return (v_now / v_then) ** (1 / years) - 1


def _yoy_growth(series: dict):
    """series: {fecha_fin: valor}. Crecimiento del último ejercicio anual
    completo frente al anterior."""
    dates = sorted(series)
    if len(dates) < 2:
        return None
    prev, last = series[dates[-2]], series[dates[-1]]
    if not prev or prev <= 0:
        return None
    return (last / prev) - 1


def compute_edgar_metrics(facts: dict) -> dict:
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

    roic = None
    common_dates = sorted(set(ni_series) & set(equity_series) & set(debt_series))
    latest_roic_date = common_dates[-1] if common_dates else None
    if latest_roic_date:
        # Aproximación: NOPAT ~ NetIncomeLoss (sin ajuste fiscal) sobre
        # capital invertido ~ patrimonio neto + deuda a largo plazo.
        invested_capital = equity_series[latest_roic_date] + debt_series[latest_roic_date]
        if invested_capital > 0:
            roic = ni_series[latest_roic_date] / invested_capital

    def _latest(series):
        return series[max(series)] if series else None

    latest_revenue = _latest(revenue_series)
    latest_ni = _latest(ni_series)
    latest_equity = _latest(equity_series)
    latest_debt = _latest(debt_series)
    latest_cash = _latest(cash_series)
    latest_gross_profit = _latest(gross_profit_series)
    latest_operating_income = _latest(operating_income_series)
    latest_da = _latest(da_series)
    latest_fcf = _latest(fcf_series)

    gross_margin = (latest_gross_profit / latest_revenue) if latest_gross_profit and latest_revenue else None
    operating_margin = (latest_operating_income / latest_revenue) if latest_operating_income and latest_revenue else None
    profit_margin = (latest_ni / latest_revenue) if latest_ni is not None and latest_revenue else None

    ebitda = None
    if latest_operating_income is not None and latest_da is not None:
        ebitda = latest_operating_income + latest_da
    net_debt = None
    if latest_debt is not None:
        net_debt = latest_debt - (latest_cash or 0)
    net_debt_to_ebitda = (net_debt / ebitda) if net_debt is not None and ebitda else None

    return {
        # Derivados ya existentes (usados hoy en el screener "en vivo").
        "revenue_cagr_3y": _cagr_from_series(sorted(revenue_series.items()), 3),
        "fcf_cagr_3y": _cagr_from_series(sorted(fcf_series.items()), 3),
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
        "earnings_growth_yoy": _yoy_growth(ni_series),
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


def _fetch_one(symbol: str, cik: str) -> tuple:
    facts = fetch_company_facts(cik)
    raw_facts = _extract_raw_facts(facts, TRACKED_TAGS, unit="USD")
    raw_facts += _extract_raw_facts(facts, SHARES_TAGS, unit="shares")
    metrics = compute_edgar_metrics(facts)
    try:
        submissions = fetch_submissions(cik)
        metrics.update(extract_latest_filings(submissions))
    except Exception:
        pass  # los enlaces a filings son un "nice to have"; no tumbar la empresa por esto
    return metrics, raw_facts


def upsert_edgar_metrics(symbol: str, cik: str, metrics: dict):
    fetched_at = datetime.now(UTC).isoformat()
    with storage.get_connection() as conn:
        conn.executescript(SCHEMA)
        conn.execute(
            "INSERT OR REPLACE INTO edgar_metrics "
            "(symbol, cik, fetched_at, revenue_cagr_3y, fcf_cagr_3y, roic, "
            "latest_10k_date, latest_10k_url, latest_10q_date, latest_10q_url) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                symbol, cik, fetched_at,
                metrics.get("revenue_cagr_3y"), metrics.get("fcf_cagr_3y"), metrics.get("roic"),
                metrics.get("latest_10k_date"), metrics.get("latest_10k_url"),
                metrics.get("latest_10q_date"), metrics.get("latest_10q_url"),
            ),
        )
        conn.commit()


def get_edgar_metrics(symbols: list) -> dict:
    if not symbols:
        return {}
    placeholders = ",".join("?" * len(symbols))
    with storage.get_connection() as conn:
        conn.executescript(SCHEMA)
        rows = conn.execute(
            f"SELECT symbol, revenue_cagr_3y, fcf_cagr_3y, roic, "
            f"latest_10k_date, latest_10k_url, latest_10q_date, latest_10q_url "
            f"FROM edgar_metrics WHERE symbol IN ({placeholders})", symbols,
        ).fetchall()
    cols = ["revenue_cagr_3y", "fcf_cagr_3y", "roic", "latest_10k_date", "latest_10k_url", "latest_10q_date", "latest_10q_url"]
    return {r[0]: dict(zip(cols, r[1:])) for r in rows}


def get_symbols_with_facts(symbols: list) -> set:
    """Símbolos con al menos una fila en edgar_facts. Sirve para distinguir
    'fetched_at reciente' de 'de verdad tiene el histórico fechado' — algunas
    empresas se descargaron antes de que existiera esta tabla (o solo se
    guardó edgar_metrics por algún fallo puntual al persistir), y sin este
    chequeo quedarían marcadas como "frescas" para siempre sin tener nunca
    los datos que hacen falta para reconstruir una fecha pasada."""
    if not symbols:
        return set()
    placeholders = ",".join("?" * len(symbols))
    with storage.get_connection() as conn:
        conn.executescript(FACTS_SCHEMA)
        rows = conn.execute(
            f"SELECT DISTINCT symbol FROM edgar_facts WHERE symbol IN ({placeholders})", symbols,
        ).fetchall()
    return {r[0] for r in rows}


def get_edgar_fetched_at(symbols: list) -> dict:
    if not symbols:
        return {}
    placeholders = ",".join("?" * len(symbols))
    with storage.get_connection() as conn:
        conn.executescript(SCHEMA)
        rows = conn.execute(
            f"SELECT symbol, fetched_at FROM edgar_metrics WHERE symbol IN ({placeholders})", symbols,
        ).fetchall()
    result = {}
    for symbol, fetched_at in rows:
        try:
            result[symbol] = datetime.fromisoformat(fetched_at)
        except Exception:
            result[symbol] = None
    return result


def fetch_edgar_batch(symbols: list, cik_by_symbol: dict, max_workers: int = 4, progress_cb=None) -> dict:
    """Descarga y cachea métricas EDGAR en paralelo (pool conservador: la SEC
    es más estricta que Yahoo con el rate limiting). Devuelve dict[symbol] =
    motivo de error en español para los símbolos que fallaron."""
    failed = {}
    total = len(symbols)
    if total == 0:
        return failed
    with cf.ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {}
        for s in symbols:
            cik = cik_by_symbol.get(s)
            if not cik:
                failed[s] = (
                    "Símbolo no encontrado en el mapeo ticker→CIK de la SEC (ni en vivo ni en "
                    "resoluciones anteriores) — posible ticker deslistado hace tiempo, o nunca resuelto antes"
                )
                continue
            futures[ex.submit(_fetch_one, s, cik)] = (s, cik)
        done = 0
        for fut in cf.as_completed(futures):
            sym, cik = futures[fut]
            done += 1
            try:
                metrics, raw_facts = fut.result()
                upsert_edgar_metrics(sym, cik, metrics)
                upsert_edgar_facts(sym, raw_facts)  # escritura en el hilo principal, no en el worker
            except Exception as exc:
                _, reason = _classify_error(exc, service="SEC EDGAR")
                failed[sym] = reason
            if progress_cb:
                progress_cb(done, total, sym)
    return failed


def ensure_edgar_data(symbols: list, force: bool = False, max_age_hours: int = None, progress_cb=None) -> dict:
    max_age_hours = max_age_hours or config.EDGAR_CACHE_MAX_AGE_HOURS
    symbols = list(dict.fromkeys(symbols))

    try:
        cik_map = get_cik_map()
    except Exception as exc:
        _, reason = _classify_error(exc, service="SEC EDGAR")
        cik_map = None
        live_map_error = reason
    else:
        live_map_error = None

    fetched_at = get_edgar_fetched_at(symbols)
    with_facts = get_symbols_with_facts(symbols)
    now = datetime.now(UTC)
    stale = [
        s for s in symbols
        if force or fetched_at.get(s) is None
        or (now - fetched_at[s]).total_seconds() > max_age_hours * 3600
        or s not in with_facts  # "fresco" pero sin histórico fechado real: hay que rellenarlo igualmente
    ]

    # Se resuelve CIK símbolo a símbolo (mapeo en vivo, con fallback a la
    # caché local de resoluciones anteriores — ver get_cik_for_symbol) en vez
    # de un solo dict global: así una empresa ya deslistada puede seguir
    # actualizándose aunque haya desaparecido del mapeo en vivo de hoy.
    cik_by_symbol = {}
    for s in stale:
        cik, _title = get_cik_for_symbol(s, cik_map=cik_map) if cik_map is not None else _get_cached_cik_resolution(s)
        if cik:
            cik_by_symbol[s] = cik

    if cik_map is None and not cik_by_symbol:
        # Sin mapeo en vivo Y sin nada en la caché local: no hay forma de
        # seguir para ninguno de los símbolos pedidos.
        return {"edgar_refreshed": 0, "failed": {s: live_map_error for s in symbols}}

    failed = fetch_edgar_batch(stale, cik_by_symbol, progress_cb=progress_cb) if stale else {}
    return {"edgar_refreshed": len(stale) - len(failed), "failed": failed}
