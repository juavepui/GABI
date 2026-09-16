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
from datetime import date, datetime, timezone

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
        if len(by_end) >= 2:
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


def _cagr_from_series(series: list, years: int = 3):
    if len(series) < years + 1:
        return None
    _, v_now = series[-1]
    _, v_then = series[-1 - years]
    if not v_then or v_then <= 0 or not v_now or v_now <= 0:
        return None
    return (v_now / v_then) ** (1 / years) - 1


def compute_edgar_metrics(facts: dict) -> dict:
    revenue_series = _extract_annual_values(facts, REVENUE_TAGS)
    ni_series = dict(_extract_annual_values(facts, NET_INCOME_TAGS))
    ocf_series = dict(_extract_annual_values(facts, OCF_TAGS))
    capex_series = dict(_extract_annual_values(facts, CAPEX_TAGS))
    equity_series = dict(_extract_instant_values(facts, EQUITY_TAGS))
    debt_series = dict(_extract_instant_values(facts, LT_DEBT_TAGS))

    fcf_series = sorted(
        (d, ocf_series[d] - abs(capex_series[d]))
        for d in (set(ocf_series) & set(capex_series))
    )

    roic = None
    common_dates = sorted(set(ni_series) & set(equity_series) & set(debt_series))
    if common_dates:
        last = common_dates[-1]
        # Aproximación: NOPAT ~ NetIncomeLoss (sin ajuste fiscal) sobre
        # capital invertido ~ patrimonio neto + deuda a largo plazo.
        invested_capital = equity_series[last] + debt_series[last]
        if invested_capital > 0:
            roic = ni_series[last] / invested_capital

    return {
        "revenue_cagr_3y": _cagr_from_series(revenue_series, 3),
        "fcf_cagr_3y": _cagr_from_series(fcf_series, 3),
        "roic": roic,
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


def _fetch_one(symbol: str, cik: str) -> dict:
    facts = fetch_company_facts(cik)
    metrics = compute_edgar_metrics(facts)
    try:
        submissions = fetch_submissions(cik)
        metrics.update(extract_latest_filings(submissions))
    except Exception:
        pass  # los enlaces a filings son un "nice to have"; no tumbar la empresa por esto
    return metrics


def upsert_edgar_metrics(symbol: str, cik: str, metrics: dict):
    fetched_at = datetime.now(timezone.utc).isoformat()
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
                failed[s] = "Símbolo no encontrado en el mapeo ticker→CIK de la SEC"
                continue
            futures[ex.submit(_fetch_one, s, cik)] = (s, cik)
        done = 0
        for fut in cf.as_completed(futures):
            sym, cik = futures[fut]
            done += 1
            try:
                metrics = fut.result()
                upsert_edgar_metrics(sym, cik, metrics)
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
        return {"edgar_refreshed": 0, "failed": {s: reason for s in symbols}}

    cik_by_symbol = dict(zip(cik_map["symbol"], cik_map["cik"]))

    fetched_at = get_edgar_fetched_at(symbols)
    now = datetime.now(timezone.utc)
    stale = [
        s for s in symbols
        if force or fetched_at.get(s) is None
        or (now - fetched_at[s]).total_seconds() > max_age_hours * 3600
    ]
    failed = fetch_edgar_batch(stale, cik_by_symbol, progress_cb=progress_cb) if stale else {}
    return {"edgar_refreshed": len(stale) - len(failed), "failed": failed}
