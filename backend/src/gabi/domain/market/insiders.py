"""Form 4 interpretation and open-market activity over explicit inputs."""

import xml.etree.ElementTree as ET
from datetime import date

import pandas as pd

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


def summarize_insider_activity(transactions: pd.DataFrame, months: int = 6, *, as_of: date) -> dict:
    """Resumen de actividad en los últimos `months` meses. Solo cuenta P
    (compra) y S (venta) en mercado abierto — concesiones, ejercicios de
    opciones y donaciones no reflejan una decisión de convicción, así que no
    cuentan para 'compradores distintos' ni para el valor neto.

    Las filas y el día de corte son entradas explícitas."""
    df = transactions
    empty = {
        "n_buys": 0, "n_sells": 0, "distinct_buyers": 0, "distinct_sellers": 0,
        "net_value": None, "has_10b5_1_only_buys": False, "recent": df,
    }
    if df.empty:
        return empty

    cutoff = (pd.Timestamp(as_of) - pd.DateOffset(months=months)).date().isoformat()
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


