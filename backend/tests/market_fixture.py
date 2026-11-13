"""Synthetic bounded data only; shared by contract tests and the measurement script."""
import json
import sqlite3
from datetime import date

import numpy as np
import pandas as pd

from gabi import edgar, identity, storage
from gabi.domain.market import model_policy
from gabi.infrastructure.legacy import blind_validation

TODAY = date(2026, 9, 29)


def seed_fixture(root, companies=12, sessions=320, *, wal=False, engine=True):
    root.mkdir(parents=True, exist_ok=True)
    symbols = [f"T{i:03}" for i in range(companies)] + ["BRK-A", "BRK-B", "SHORT", "EMPTY"]
    universe = pd.DataFrame({"symbol": symbols, "name": [f"Company {s}" for s in symbols],
                             "sector": ["Information Technology"] * companies + ["Financials"] * 4})
    universe.to_csv(root / "sp500_constituents.csv", index=False)
    (root / "weights.json").write_text(json.dumps(dict(model_policy.FROZEN_WEIGHTS)), encoding="utf-8")
    connection = sqlite3.connect(root / "gabi.db")
    if wal:
        connection.execute("PRAGMA journal_mode=WAL")
    connection.executescript(storage.SCHEMA + edgar.SCHEMA + identity.SCHEMA + blind_validation.SCHEMA)
    connection.executescript("CREATE TABLE macro_series(series_id,date,value); "
                             "CREATE TABLE experiments(stage,returns_json,result_json); "
                             "INSERT INTO macro_series VALUES('DGS10','2026-09-29',4.25);")
    rng = np.random.default_rng(64)
    dates = pd.bdate_range(end=TODAY, periods=sessions)
    for i, symbol in enumerate(symbols[:-1] + ["SPY"]):
        series = 100 * np.cumprod(1 + rng.normal(0.0008 + i * 0.00002, 0.008, sessions))
        actual_dates = dates[-5:] if symbol == "SHORT" else dates
        actual_series = series[-5:] if symbol == "SHORT" else series
        connection.executemany("INSERT INTO prices VALUES(?,?,?,?,?,?,?,?)", [
            (symbol, day.date().isoformat(), float(price), float(price * 1.01), float(price * 0.99),
             float(price), 100000., None if symbol == "BRK-B" and j == 0 else float(price * 0.95))
            for j, (day, price) in enumerate(zip(actual_dates, actual_series, strict=True))])
        if symbol == "SPY":
            continue
        info = {"marketCap": 1e9 * (i + 1), "trailingPE": 10 + i, "priceToBook": 1 + i / 10,
                "enterpriseToEbitda": 7 + i / 10, "returnOnEquity": 0.12, "operatingMargins": .15 + i / 100,
                "debtToEquity": 30 + i, "revenueGrowth": .05, "freeCashflow": 1e8, "averageDailyVolume3Month": 1e5}
        if symbol == "SHORT":
            info = {"marketCap": 8e8, "trailingPE": -1}
        connection.execute("INSERT INTO fundamentals VALUES(?,?,?,?,?)",
                           (symbol, "2026-09-29T08:00:00+00:00", json.dumps(info), "{}", "{}"))
        if symbol != "SHORT":
            connection.execute("INSERT INTO edgar_metrics VALUES(?,?,?,?,?,?,?,?,?,?)",
                               (symbol, "0000000001", "2026-09-29T08:00:00+00:00", .05 + i / 100, .08,
                                .10 + i / 1000, "2026-02-01", "https://www.sec.gov/Archives/fixture.htm", None, None))
    connection.execute("INSERT INTO entities VALUES('issuer','0000000001','Issuer','2026-01-01')")
    for symbol in ("BRK-A", "BRK-B"):
        connection.execute("INSERT INTO entity_aliases VALUES(?,?,?,?,?,?)",
                           ("issuer", symbol, "2026-01-01", None, "fixture:reviewed", 1.))
    connection.commit()
    connection.close()
    if engine:
        seed_engine_fundamentals(root, symbols[:companies] + ["BRK-A", "BRK-B"])
    return universe


def seed_engine_fundamentals(root, symbols, as_of=TODAY):
    """#347: the tested engine's company metrics for GABI-MF-v5, consistent with the fixture's Yahoo values."""
    from datetime import UTC, datetime

    from gabi.domain.market import engine_fundamentals
    from gabi.infrastructure.storage.engine_fundamentals import SqliteEngineFundamentals

    all_symbols = [f"T{i:03}" for i in range(1000)] + ["BRK-A", "BRK-B"]
    table = pd.DataFrame({
        "pe": [10. + all_symbols.index(s) for s in symbols], "pb": [1 + all_symbols.index(s) / 10 for s in symbols],
        "ev_ebitda": [7 + all_symbols.index(s) / 10 for s in symbols],
        "roic": [.10 + all_symbols.index(s) / 1000 for s in symbols],
        "operating_margin": [.15 + all_symbols.index(s) / 100 for s in symbols],
        "revenue_cagr_3y": [.05 + all_symbols.index(s) / 100 for s in symbols], "fcf_cagr_3y": [.08] * len(symbols),
        "debt_to_equity": [.30 + all_symbols.index(s) / 100 for s in symbols]}, index=symbols)
    rows = engine_fundamentals.rows(table, as_of)
    SqliteEngineFundamentals(root / "gabi.db").replace(rows, datetime(2026, 9, 29, 8, tzinfo=UTC))
