"""Real holdings (#181): purchases, sales and dividends (#294), the broker CSV and their valuation.

Each movement has a ``kind``: ``buy`` and ``sell`` carry shares and a price per share; ``dividend``
carries the gross amount received in ``price`` (``shares`` 0) and the tax withheld in ``withholding``.
A sale never exceeds the shares held that day and a dividend needs shares held; the cost of what is
sold leaves at the average cost (realized gain). Values use the cached close and convert with the
cached exchange rate of the same session. A purchase converts with the rate the broker applied when the lot records it, else
with the cached rate of the purchase date. SPY bought with the same euros on the same dates is the
benchmark. Nothing here downloads: a missing price or rate is reported, never filled in.
"""

import csv
import re
from datetime import date

import pandas as pd

from gabi.domain.portfolio.simulation import fx_at, fx_symbol

BASE_CURRENCY = "EUR"
CURRENCIES = ("USD", "EUR", "GBP")
SYMBOL = re.compile(r"[A-Z0-9^][A-Z0-9^\-]{0,19}")
CSV_COLUMNS = ("symbol", "shares", "price", "date", "currency", "commission", "type", "withholding", "basis_date")
KINDS = ("buy", "sell", "dividend")
CSV_KINDS = {"": "buy", "buy": "buy", "compra": "buy", "sell": "sell", "venta": "sell",
             "dividend": "dividend", "dividendo": "dividend"}
EPSILON = 1e-9
MAX_CSV_BYTES = 100_000
MAX_SYMBOLS = 29  # The bounded price reader admits 30 symbols, SPY included.
LOOKBACK_DAYS = 7


def validate_lot(lot: dict, today: date) -> dict:
    """The stored form of a lot, or ValueError with the reason in Spanish."""
    symbol = str(lot.get("symbol") or "").strip().upper().replace(".", "-")
    if not SYMBOL.fullmatch(symbol):
        raise ValueError(f"Símbolo no válido: {lot.get('symbol')!r}.")
    currency = str(lot.get("currency") or "USD").strip().upper()
    if currency not in CURRENCIES:
        raise ValueError(f"Divisa no admitida: {currency} (USD, EUR o GBP).")
    kind = str(lot.get("kind") or "buy").strip().lower()
    if kind not in KINDS:
        raise ValueError(f"Tipo de movimiento no válido: {kind!r} (compra, venta o dividendo).")
    try:
        shares, price = float(lot.get("shares") or 0), float(lot["price"])
        commission = float(lot.get("commission") or 0)
        withholding = float(lot.get("withholding") or 0)
        fx_rate = None if lot.get("fx_rate") in (None, "") else float(lot["fx_rate"])
        purchase = lot["purchase_date"] if isinstance(lot["purchase_date"], date) \
            else date.fromisoformat(str(lot["purchase_date"]).strip())
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Acciones, precio, comisión y fecha (AAAA-MM-DD) deben ser válidos.") from exc
    if kind == "dividend":
        if not (0 < price <= 1e9 and 0 <= withholding <= price and commission == 0):
            raise ValueError("Un dividendo necesita el importe bruto positivo y una retención entre 0 y ese importe.")
        shares = 0.0
    elif not (0 < shares <= 1e9 and 0 < price <= 1e9 and 0 <= commission <= 1e9) or withholding:
        raise ValueError("Acciones y precio deben ser positivos y la comisión no negativa.")
    if fx_rate is not None and not 0 < fx_rate <= 1e6:
        raise ValueError("El tipo de cambio debe ser positivo.")
    if currency == BASE_CURRENCY:
        fx_rate = None
    if not date(1970, 1, 1) <= purchase <= today:
        raise ValueError("La fecha del movimiento no puede ser futura.")
    try:
        basis = date.fromisoformat(str(lot.get("basis_date") or purchase.isoformat()))
    except ValueError as exc:
        raise ValueError("La fecha de ajuste de acciones y precio debe ser válida (AAAA-MM-DD).") from exc
    if not purchase <= basis <= today:
        raise ValueError("La fecha de ajuste debe estar entre el movimiento y hoy.")
    note = str(lot.get("note") or "").strip()[:200] or None
    return {"symbol": symbol, "kind": kind, "shares": shares, "price": price, "purchase_date": purchase.isoformat(),
            "currency": currency, "commission": commission, "withholding": withholding, "fx_rate": fx_rate,
            "note": note, "basis_date": basis.isoformat() if lot.get('basis_date') else None}


def kind(lot: dict) -> str:
    """Rows stored before #294 have no kind: they are purchases."""
    return lot.get("kind") or "buy"


def check_sequence(lots: list[dict]) -> None:
    """Never sell more than held that day, nor receive a dividend without shares; ValueError says where.

    On one day purchases count before sales, and dividends need shares held before that day's sales."""
    order = {"buy": 0, "dividend": 1, "sell": 2}
    held: dict[str, float] = {}
    for lot in sorted(lots, key=lambda row: (row["purchase_date"], order[kind(row)], row.get("id") or 0)):
        symbol, current = lot["symbol"], held.get(lot["symbol"], 0.0)
        if kind(lot) == "buy":
            held[symbol] = current + lot["shares"]
        elif kind(lot) == "sell":
            if lot["shares"] > current + EPSILON:
                raise ValueError(f"No puedes vender {lot['shares']:g} acciones de {symbol} el {lot['purchase_date']}: "
                                 f"ese día tenías {current:g}.")
            held[symbol] = max(current - lot["shares"], 0.0)
        elif current <= EPSILON:
            raise ValueError(f"Dividendo de {symbol} el {lot['purchase_date']} sin acciones en cartera ese día.")


def _number(text: str, decimal_comma: bool) -> str:
    text = text.strip()
    return text.replace(".", "").replace(",", ".") if decimal_comma and "," in text else text


def _kind(text: str | None) -> str:
    value = str(text or "").strip().lower()
    if value not in CSV_KINDS:
        raise ValueError(f"Tipo no válido: {text!r} (compra, venta o dividendo).")
    return CSV_KINDS[value]


def parse_csv(text: str, today: date) -> list[dict]:
    """Movements of the generic broker CSV: symbol,shares,price,date,currency,commission[,type,withholding].

    ``type`` is compra (default), venta or dividendo; a dividend's ``price`` is the gross amount.

    `;` separates columns when the header uses it, and then a decimal comma is accepted. Every row must
    be valid: one wrong row rejects the file, naming its line."""
    if len(text.encode("utf-8")) > MAX_CSV_BYTES:
        raise ValueError("El CSV supera 100 KB.")
    lines = text.lstrip("﻿").strip().splitlines()
    if not lines:
        raise ValueError("El CSV está vacío.")
    delimiter = ";" if lines[0].count(";") > lines[0].count(",") else ","
    reader = csv.DictReader(lines, delimiter=delimiter)
    header = [str(name).strip().lower() for name in reader.fieldnames or []]
    missing = [column for column in CSV_COLUMNS[:4] if column not in header]
    if missing:
        raise ValueError("Faltan columnas: " + ", ".join(missing) + ". Cabecera: " + ",".join(CSV_COLUMNS) + ".")
    reader.fieldnames = header
    lots, errors = [], []
    for number, row in enumerate(reader, start=2):
        if not any((value or "").strip() for value in row.values() if isinstance(value, str)):
            continue
        try:
            lots.append(validate_lot({
                "symbol": row.get("symbol"), "currency": row.get("currency") or "USD",
                "shares": _number(row.get("shares") or "", delimiter == ";"),
                "price": _number(row.get("price") or "", delimiter == ";"),
                "commission": _number(row.get("commission") or "0", delimiter == ";"),
                "purchase_date": row.get("date"), "kind": _kind(row.get("type")),
                "withholding": _number(row.get("withholding") or "0", delimiter == ";"),
                "basis_date": row.get("basis_date")}, today))
        except ValueError as exc:
            errors.append(f"línea {number}: {exc}")
    if errors:
        raise ValueError("; ".join(errors[:5]) + (f" (y {len(errors) - 5} más)" if len(errors) > 5 else ""))
    if not lots:
        raise ValueError("El CSV no tiene filas.")
    return lots


def price_symbols(lots: list[dict]) -> list[str]:
    """What a valuation reads, and what the explicit price action downloads: holdings, SPY and the rates."""
    symbols = list(dict.fromkeys(lot["symbol"] for lot in lots))
    pairs = {pair for currency in [*(lot["currency"] for lot in lots), "USD"]
             if (pair := fx_symbol(currency, BASE_CURRENCY))}
    return symbols + ["SPY"] + sorted(pairs)


def _close(histories: dict, symbol: str, day: pd.Timestamp | None = None) -> tuple[pd.Timestamp, float] | None:
    """The last cached close on or before `day` (the latest one without it), within the lookback for a day."""
    history = histories.get(symbol)
    if history is None or history.empty or "close" not in history:
        return None
    closes = history["close"].dropna()
    closes = closes[closes > 0]
    if day is not None:
        closes = closes[(closes.index <= day) & (closes.index >= day - pd.Timedelta(days=LOOKBACK_DAYS))]
    if closes.empty:
        return None
    return closes.index[-1], float(closes.iloc[-1])


def _rate(histories: dict, currency: str, day) -> float | None:
    try:
        return fx_at(histories, currency, BASE_CURRENCY, day)
    except ValueError:
        return None


def _in_order(lots: list[dict]) -> list[dict]:
    order = {"buy": 0, "dividend": 1, "sell": 2}
    return sorted(lots, key=lambda row: (row["purchase_date"], order[kind(row)], row.get("id") or 0))


def value(lots: list[dict], histories: dict) -> dict:
    """Open positions by symbol in their own currency and in euros, with SPY over the same purchases.

    A sale removes its share of the cost at the average cost (and the same share of the SPY bought
    with it); the difference with what it raised is the realized gain. Dividends add their net amount.
    Fully sold symbols appear in ``closed`` with their realized gain and dividends."""
    spy_now = _close(histories, "SPY")
    usd_now = None if spy_now is None else _rate(histories, "USD", spy_now[0])
    positions: dict[str, dict] = {}
    for lot in _in_order(lots):
        symbol, currency, movement = lot["symbol"], lot["currency"], kind(lot)
        day = pd.Timestamp(lot["purchase_date"])
        rate = lot["fx_rate"] if lot.get("fx_rate") else _rate(histories, currency, day)
        position = positions.setdefault(symbol, {
            "symbol": symbol, "currency": currency, "shares": 0.0, "cost": 0.0, "cost_eur": 0.0, "lots": 0,
            "first_purchase": lot["purchase_date"], "missing_buy_rate": False, "spy_eur": 0.0, "spy_usd": 0.0,
            "spy_cost_usd": 0.0, "missing_spy": spy_now is None, "realized_eur": 0.0, "dividends_eur": 0.0,
            "missing_flow_rate": False, "sales": 0, "dividends": 0})
        if position["currency"] != currency:
            raise ValueError(f"{symbol} tiene movimientos en dos divisas.")
        if movement == "dividend":
            position["dividends"] += 1
            if rate is None:
                position["missing_flow_rate"] = True
            else:
                position["dividends_eur"] += (lot["price"] - (lot.get("withholding") or 0)) * rate
            continue
        if movement == "sell":
            held = position["shares"]
            share = min(lot["shares"] / held, 1.0) if held > EPSILON else 1.0
            removed_eur = position["cost_eur"] * share
            for key in ("cost", "cost_eur", "spy_eur", "spy_usd", "spy_cost_usd"):
                position[key] *= 1 - share
            position["shares"] = max(held - lot["shares"], 0.0)
            position["sales"] += 1
            proceeds = lot["shares"] * lot["price"] - lot["commission"]
            if rate is None or position["missing_buy_rate"]:
                position["missing_flow_rate"] = True
            else:
                position["realized_eur"] += proceeds * rate - removed_eur
            continue
        cost = lot["shares"] * lot["price"] + lot["commission"]
        position["shares"] += lot["shares"]
        position["cost"] += cost
        position["lots"] += 1
        position["first_purchase"] = min(position["first_purchase"], lot["purchase_date"])
        if rate is None:
            position["missing_buy_rate"] = True
        else:
            position["cost_eur"] += cost * rate
        spy_then = _close(histories, "SPY", day)
        usd_then = None if spy_then is None else _rate(histories, "USD", spy_then[0])
        if spy_then is None or spy_now is None:
            position["missing_spy"] = True
            continue
        # The same money buys SPY on the same date: in dollars always, in euros when both rates exist.
        cost_usd = cost if currency == "USD" else None
        if cost_usd is not None:
            position["spy_cost_usd"] += cost_usd
            position["spy_usd"] += cost_usd / spy_then[1] * spy_now[1]
        if rate is not None and usd_then and usd_now:
            position["spy_eur"] += cost * rate / (spy_then[1] * usd_then) * spy_now[1] * usd_now
        else:
            position["missing_spy"] = True
    rows, closed = [], []
    for position in positions.values():
        flows_ok = not position["missing_flow_rate"]
        income = {"realized_eur": position["realized_eur"] if flows_ok else None,
                  "dividends_eur": position["dividends_eur"] if flows_ok else None,
                  "sales": position["sales"], "dividends": position["dividends"]}
        if position["shares"] <= EPSILON:
            closed.append({"symbol": position["symbol"], "currency": position["currency"], **income})
            continue
        current = _close(histories, position["symbol"])
        now_rate = None if current is None else _rate(histories, position["currency"], current[0])
        shares, cost = position["shares"], position["cost"]
        market_value = None if current is None else shares * current[1]
        value_eur = None if market_value is None or now_rate is None else market_value * now_rate
        cost_eur = None if position["missing_buy_rate"] else position["cost_eur"]
        status = "missing_price" if current is None else "missing_fx" if value_eur is None or cost_eur is None \
            else "ok"
        spy_eur = None if position["missing_spy"] or cost_eur is None else position["spy_eur"]
        rows.append({
            "symbol": position["symbol"], "currency": position["currency"], "shares": shares, "lots": position["lots"],
            "first_purchase": position["first_purchase"], "average_price": (cost / shares) if shares else None,
            "price": None if current is None else current[1],
            "price_date": None if current is None else current[0].date().isoformat(),
            "cost": cost, "value": market_value,
            "price_return": None if market_value is None else market_value / cost - 1,
            "spy_return_usd": (position["spy_usd"] / position["spy_cost_usd"] - 1)
            if position["spy_cost_usd"] and not position["missing_spy"] else None,
            "cost_eur": cost_eur, "value_eur": value_eur,
            "return_eur": None if value_eur is None or not cost_eur else value_eur / cost_eur - 1,
            "spy_value_eur": spy_eur,
            "spy_return_eur": None if spy_eur is None or not cost_eur else spy_eur / cost_eur - 1,
            "status": status, **income})
    valued = [row for row in rows if row["status"] == "ok"]
    cost_eur = sum(row["cost_eur"] for row in valued)
    value_eur = sum(row["value_eur"] for row in valued)
    benchmarked = [row for row in valued if row["spy_value_eur"] is not None]
    spy_cost = sum(row["cost_eur"] for row in benchmarked)
    spy_value = sum(row["spy_value_eur"] for row in benchmarked)
    for row in rows:
        row["weight_pct"] = row["value_eur"] / value_eur * 100 if row["status"] == "ok" and value_eur else None
    every = [*rows, *closed]
    complete_income = all(row["realized_eur"] is not None for row in every)
    return {
        "positions": sorted(rows, key=lambda row: (-(row["value_eur"] or 0), row["symbol"])),
        "closed": sorted(closed, key=lambda row: row["symbol"]),
        "totals": {"cost_eur": cost_eur if valued else None, "value_eur": value_eur if valued else None,
                   "return_eur": value_eur / cost_eur - 1 if cost_eur else None,
                   "spy_return_eur": spy_value / spy_cost - 1 if spy_cost and len(benchmarked) == len(valued)
                   else None,
                   "realized_eur": sum(row["realized_eur"] for row in every) if complete_income else None,
                   "dividends_eur": sum(row["dividends_eur"] for row in every) if complete_income else None,
                   "valued": len(valued), "positions": len(rows), "complete": len(valued) == len(rows)},
        "benchmark_as_of": None if spy_now is None else spy_now[0].date().isoformat(),
    }


def deviations(positions: list[dict], target: dict[str, float]) -> list[dict]:
    """Current weight against the frozen target weight, for held symbols and target symbols not held."""
    current = {row["symbol"]: row["weight_pct"] for row in positions}
    rows = []
    for symbol in list(dict.fromkeys([*current, *target])):
        weight, goal = current.get(symbol), target.get(symbol, 0.0)
        rows.append({"symbol": symbol, "weight_pct": weight if symbol in current else 0.0, "target_pct": goal,
                     "deviation_pp": None if symbol in current and weight is None else (weight or 0.0) - goal})
    return sorted(rows, key=lambda row: (-abs(row["deviation_pp"] or 0), row["symbol"]))
