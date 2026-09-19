"""Operaciones de insiders (consejeros, directivos, accionistas >10%) desde
los Form 4 de SEC EDGAR (Section 16) — gratis, sin API key.

Es la señal de "qué sabe la dirección que el mercado no sabe todavía" que le
faltaba a GABI: ni yfinance ni el resto de fuentes ya integradas la dan. Una
compra en mercado abierto con dinero propio (código P) es mucho más
informativa que una venta rutinaria, un ejercicio de opciones o una
operación dentro de un plan 10b5-1 programado con meses de antelación — por
eso se distinguen explícitamente en vez de mezclarlas todas como "actividad
de insiders" sin más.

De momento es solo informativo (se muestra en la Ficha de empresa): no entra
en el Composite Score. Igual que con el resto de bloques nuevos, primero hay
que ver si la señal aporta algo con datos reales antes de dejar que vote."""
import xml.etree.ElementTree as ET
from datetime import UTC, datetime

import pandas as pd
import requests

from . import config, edgar, storage
from .data_fetch import _classify_error

TRANSACTION_CODES = {
    "P": "Compra en mercado abierto",
    "S": "Venta en mercado abierto",
    "A": "Concesión/adjudicación (award)",
    "M": "Ejercicio de opciones",
    "G": "Donación (gift)",
    "F": "Retención fiscal (tax withholding)",
    "C": "Conversión de valores derivados",
    "X": "Ejercicio de opción in-the-money",
    "D": "Disposición a un tercero (ej. divorcio)",
    "J": "Otra transacción (ver notas del filing)",
}
# Las únicas dos que reflejan una decisión discrecional con dinero/acciones
# propias en mercado abierto — el resto son mecánicas (compensación, fiscal,
# ejercicio de opciones) y no se cuentan como señal de convicción.
SIGNAL_CODES = {"P", "S"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS insider_transactions (
    symbol TEXT NOT NULL,
    cik TEXT NOT NULL,
    accn TEXT NOT NULL,
    line_no INTEGER NOT NULL,
    owner_name TEXT,
    owner_title TEXT,
    is_officer INTEGER,
    is_director INTEGER,
    is_ten_pct_owner INTEGER,
    is_10b5_1_plan INTEGER,
    transaction_date TEXT NOT NULL,
    transaction_code TEXT NOT NULL,
    acquired_disposed TEXT,
    shares REAL,
    price_per_share REAL,
    shares_owned_after REAL,
    filed_date TEXT,
    PRIMARY KEY (symbol, accn, line_no)
);
CREATE INDEX IF NOT EXISTS idx_insider_symbol_date ON insider_transactions (symbol, transaction_date);
CREATE TABLE IF NOT EXISTS insider_fetch_meta (
    symbol TEXT PRIMARY KEY,
    fetched_at TEXT NOT NULL
);
"""


def _text(elem, path):
    if elem is None:
        return None
    node = elem.find(path)
    return node.text.strip() if node is not None and node.text else None


def _bool(elem, path):
    val = _text(elem, path)
    return val is not None and val.strip().lower() == "true"


def _float(elem, path):
    val = _text(elem, path)
    try:
        return float(val) if val is not None else None
    except ValueError:
        return None


def parse_form4_xml(xml_text: str) -> dict:
    """Extrae del XML crudo de un Form 4: quién es el insider, su relación
    con la empresa (directivo/consejero/accionista >10%), si las
    transacciones parecen ir dentro de un plan 10b5-1 (por las notas al
    pie — SEC no lo marca con un campo aparte), y cada transacción de
    acciones ordinarias (no derivados: opciones/warrants se ignoran, son
    una señal mucho más ambigua)."""
    root = ET.fromstring(xml_text)
    issuer_symbol = _text(root, "issuer/issuerTradingSymbol")
    owner = root.find("reportingOwner")
    owner_name = _text(owner, "reportingOwnerId/rptOwnerName")
    rel = owner.find("reportingOwnerRelationship") if owner is not None else None
    is_officer = _bool(rel, "isOfficer")
    is_director = _bool(rel, "isDirector")
    is_ten_pct = _bool(rel, "isTenPercentOwner")
    officer_title = _text(rel, "officerTitle")

    footnote_text = " ".join((fn.text or "") for fn in root.findall(".//footnote")).lower()
    is_10b5_1 = "10b5-1" in footnote_text.replace(" ", "")

    transactions = []
    for i, tx in enumerate(root.findall(".//nonDerivativeTransaction")):
        code = _text(tx, "transactionCoding/transactionCode")
        date = _text(tx, "transactionDate/value")
        if not code or not date:
            continue
        transactions.append({
            "line_no": i,
            "transaction_date": date,
            "transaction_code": code,
            "acquired_disposed": _text(tx, "transactionAmounts/transactionAcquiredDisposedCode/value"),
            "shares": _float(tx, "transactionAmounts/transactionShares/value"),
            "price_per_share": _float(tx, "transactionAmounts/transactionPricePerShare/value"),
            "shares_owned_after": _float(tx, "postTransactionAmounts/sharesOwnedFollowingTransaction/value"),
        })

    return {
        "symbol": issuer_symbol, "owner_name": owner_name, "owner_title": officer_title,
        "is_officer": is_officer, "is_director": is_director, "is_ten_pct_owner": is_ten_pct,
        "is_10b5_1_plan": is_10b5_1, "transactions": transactions,
    }


def fetch_insider_transactions(symbol: str, cik: str, limit_filings: int = 20) -> list:
    """Descarga y parsea los Form 4 más recientes de una empresa (los Form 3
    y 5 no traen transacciones, solo posiciones iniciales/anuales, así que
    se ignoran). limit_filings acota cuántos filings recientes mirar — no
    hace falta el histórico completo para una señal de actividad reciente."""
    submissions = edgar.fetch_submissions(cik)
    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accessions = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])
    filing_dates = recent.get("filingDate", [])

    rows = []
    count = 0
    for i, form in enumerate(forms):
        if form != "4" or count >= limit_filings:
            continue
        count += 1
        accn_nodash = accessions[i].replace("-", "")
        filename = primary_docs[i].split("/")[-1]  # la carpeta xslF345X06/ es la vista renderizada; el XML crudo vive en la raíz del accession
        url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn_nodash}/{filename}"
        try:
            resp = requests.get(url, headers={"User-Agent": config.SEC_USER_AGENT}, timeout=20)
            resp.raise_for_status()
            parsed = parse_form4_xml(resp.text)
        except Exception:
            continue  # un filing individual mal formado no debe tumbar el resto
        for tx in parsed["transactions"]:
            rows.append({
                "symbol": symbol, "cik": cik, "accn": accessions[i],
                "owner_name": parsed["owner_name"], "owner_title": parsed["owner_title"],
                "is_officer": parsed["is_officer"], "is_director": parsed["is_director"],
                "is_ten_pct_owner": parsed["is_ten_pct_owner"], "is_10b5_1_plan": parsed["is_10b5_1_plan"],
                "filed_date": filing_dates[i] if i < len(filing_dates) else None,
                **tx,
            })
    return rows


def upsert_insider_transactions(symbol: str, rows: list):
    with storage.get_connection() as conn:
        conn.executescript(SCHEMA)
        if rows:
            conn.executemany(
                "INSERT OR REPLACE INTO insider_transactions "
                "(symbol, cik, accn, line_no, owner_name, owner_title, is_officer, is_director, "
                "is_ten_pct_owner, is_10b5_1_plan, transaction_date, transaction_code, acquired_disposed, "
                "shares, price_per_share, shares_owned_after, filed_date) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [
                    (
                        r["symbol"], r["cik"], r["accn"], r["line_no"], r["owner_name"], r["owner_title"],
                        int(r["is_officer"]), int(r["is_director"]), int(r["is_ten_pct_owner"]),
                        int(r["is_10b5_1_plan"]), r["transaction_date"], r["transaction_code"],
                        r["acquired_disposed"], r["shares"], r["price_per_share"], r["shares_owned_after"],
                        r["filed_date"],
                    )
                    for r in rows
                ],
            )
        conn.execute(
            "INSERT OR REPLACE INTO insider_fetch_meta (symbol, fetched_at) VALUES (?, ?)",
            (symbol, datetime.now(UTC).isoformat()),
        )
        conn.commit()


def get_insider_transactions(symbol: str) -> pd.DataFrame:
    with storage.get_connection() as conn:
        conn.executescript(SCHEMA)
        return pd.read_sql_query(
            "SELECT * FROM insider_transactions WHERE symbol = ? ORDER BY transaction_date DESC",
            conn, params=(symbol,),
        )


def get_insider_fetched_at(symbols: list) -> dict:
    if not symbols:
        return {}
    placeholders = ",".join("?" * len(symbols))
    with storage.get_connection() as conn:
        conn.executescript(SCHEMA)
        rows = conn.execute(
            f"SELECT symbol, fetched_at FROM insider_fetch_meta WHERE symbol IN ({placeholders})", symbols,
        ).fetchall()
    result = {}
    for symbol, fetched_at in rows:
        try:
            result[symbol] = datetime.fromisoformat(fetched_at)
        except Exception:
            result[symbol] = None
    return result


def summarize_insider_activity(symbol: str, months: int = 6) -> dict:
    """Resumen de actividad en los últimos `months` meses. Solo cuenta P
    (compra) y S (venta) en mercado abierto — concesiones, ejercicios de
    opciones y donaciones no reflejan una decisión de convicción, así que no
    cuentan para 'compradores distintos' ni para el valor neto."""
    df = get_insider_transactions(symbol)
    empty = {
        "n_buys": 0, "n_sells": 0, "distinct_buyers": 0, "distinct_sellers": 0,
        "net_value": None, "has_10b5_1_only_buys": False, "recent": df,
    }
    if df.empty:
        return empty

    cutoff = (pd.Timestamp.now(tz="UTC").tz_localize(None) - pd.DateOffset(months=months)).date().isoformat()
    recent = df[df["transaction_date"] >= cutoff]
    if recent.empty:
        return {**empty, "recent": recent}

    buys = recent[recent["transaction_code"] == "P"]
    sells = recent[recent["transaction_code"] == "S"]
    net_value = None
    if not buys.empty or not sells.empty:
        buy_value = (buys["shares"].fillna(0) * buys["price_per_share"].fillna(0)).sum()
        sell_value = (sells["shares"].fillna(0) * sells["price_per_share"].fillna(0)).sum()
        net_value = float(buy_value - sell_value)

    return {
        "n_buys": int(len(buys)), "n_sells": int(len(sells)),
        "distinct_buyers": int(buys["owner_name"].nunique()),
        "distinct_sellers": int(sells["owner_name"].nunique()),
        "net_value": net_value,
        "has_10b5_1_only_buys": bool(not buys.empty and buys["is_10b5_1_plan"].astype(bool).all()),
        "recent": recent,
    }


def ensure_insider_data(symbols: list, max_age_hours: int = None, max_workers: int = 4, progress_cb=None) -> dict:
    """Descarga/refresca Form 4 de los símbolos dados (por defecto, cada 24h
    — la actividad de insiders cambia más a menudo que unos fundamentales
    anuales, así que se refresca más seguido que SEC EDGAR fundamental)."""
    import concurrent.futures as cf

    max_age_hours = max_age_hours or 24
    symbols = list(dict.fromkeys(symbols))

    try:
        cik_map = edgar.get_cik_map()
    except Exception as exc:
        _, reason = _classify_error(exc, service="SEC EDGAR")
        return {"refreshed": 0, "failed": {s: reason for s in symbols}}

    fetched_at = get_insider_fetched_at(symbols)
    now = datetime.now(UTC)
    stale = [
        s for s in symbols
        if fetched_at.get(s) is None or (now - fetched_at[s]).total_seconds() > max_age_hours * 3600
    ]
    if not stale:
        return {"refreshed": 0, "failed": {}}

    cik_by_symbol = {}
    for s in stale:
        cik, _title = edgar.get_cik_for_symbol(s, cik_map=cik_map)
        if cik:
            cik_by_symbol[s] = cik

    failed = {}
    total = len(stale)
    done = 0
    with cf.ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {}
        for s in stale:
            cik = cik_by_symbol.get(s)
            if not cik:
                failed[s] = "Símbolo no encontrado en el mapeo ticker→CIK de la SEC"
                continue
            futures[ex.submit(fetch_insider_transactions, s, cik)] = s
        for fut in cf.as_completed(futures):
            sym = futures[fut]
            done += 1
            try:
                rows = fut.result()
                upsert_insider_transactions(sym, rows)
            except Exception as exc:
                _, reason = _classify_error(exc, service="SEC EDGAR")
                failed[sym] = reason
            if progress_cb:
                progress_cb(done, total, sym)

    return {"refreshed": len(stale) - len(failed), "failed": failed}
