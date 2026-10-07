"""Published current-map resolution; no inference from historical ticker reuse."""

import pandas as pd


def mapping_rows(payload: dict) -> list[dict]:
    return [{"symbol": value["ticker"], "cik": str(value["cik_str"]).zfill(10),
             "title": value.get("title", "")} for value in payload.values()]


def lookup(symbol: str, mapping: pd.DataFrame) -> tuple | None:
    row = mapping[mapping["symbol"] == symbol]
    if row.empty and "." in symbol:
        row = mapping[mapping["symbol"] == symbol.replace(".", "-")]
    if row.empty:
        return None
    return row.iloc[0]["cik"], row.iloc[0]["title"]
