"""Accredited historical series and settlement with explicit local read ports."""

from datetime import date, timedelta
from typing import Protocol

import pandas as pd

from gabi.domain.research import historical_pit as rules


class HistoricalPitReader(Protocol):
    def provenance(self, entity_id: str) -> list[tuple]: ...
    def prices(self, source_id: str, symbol: str, start: str, end: str) -> pd.DataFrame: ...
    def terminal_event(self, entity_id: str, start: str, end: str) -> dict | None: ...
    def split_factor(self, symbol: str, as_of: str) -> float: ...


def intervals(reader: HistoricalPitReader, entity_id: str, producers: set[str]) -> list[tuple]:
    result = []
    for *row, evidence in reader.provenance(entity_id):
        producer = next((ref.get("producer") for ref in evidence
                         if ref.get("kind") == "source" and ref.get("producer")), None)
        if producer is None or producer in producers:
            result.append(tuple(row))
    return result


def series_for(reader: HistoricalPitReader, entity_id: str, row: tuple) -> pd.DataFrame:
    source, symbol, start, end, status = row
    frame = reader.prices(source, symbol, start, end)
    frame.attrs.update(entity_id=entity_id, source_id=source, source_symbol=symbol,
                       valid_from=start, valid_to=end, price_source_status=status)
    return frame


def ranking_series(reader: HistoricalPitReader, entity_id: str | None, as_of: str, *, producers: set[str],
                   quarter_ends: set[str], trailing_days: int) -> pd.DataFrame:
    if not entity_id:
        return pd.DataFrame()
    day = as_of[:10]
    # Decode provenance once per issuer; never query each interval again.
    rows = []
    for *row, evidence in reader.provenance(entity_id):
        producer = next((ref.get("producer") for ref in evidence
                         if ref.get("kind") == "source" and ref.get("producer")), None)
        windows = next((ref["windows"] for ref in evidence if ref.get("kind") == "accredited_windows"), None)
        if (producer is None or producer in producers) and rules.rankable(windows, day, quarter_ends):
            rows.append(tuple(row))
    trailing = (date.fromisoformat(day) - timedelta(days=trailing_days)).isoformat()
    selected = rules._pick(rows, covering=(trailing, day)) or rules._pick(rows, covering=(day, day))
    if selected is None:
        return pd.DataFrame()
    frame = series_for(reader, entity_id, selected)
    return frame[frame.index <= pd.Timestamp(day)]


def holding_series(reader: HistoricalPitReader, entity_id: str | None, day: str, *, producers: set[str]) -> pd.DataFrame:
    if not entity_id:
        return pd.DataFrame()
    rows = [row for row in intervals(reader, entity_id, producers) if row[2] <= day[:10] < row[3]]
    if not rows:
        return pd.DataFrame()
    furthest = max(row[3] for row in rows)
    row = sorted([row for row in rows if row[3] == furthest], key=lambda row: (row[0] != rules.YAHOO_SOURCE, row[0]))[0]
    return series_for(reader, entity_id, row)


def as_traded_close(reader: HistoricalPitReader, frame: pd.DataFrame, as_of: str) -> float | None:
    if frame[frame.index <= pd.Timestamp(as_of)].empty:
        return None
    factor = reader.split_factor(frame.attrs["source_symbol"], as_of) if frame.attrs.get("source_id") == rules.YAHOO_SOURCE else 1.0
    return rules.as_traded_close(frame, as_of, factor)


def exit_value(reader: HistoricalPitReader, frame: pd.DataFrame, entity_id: str, entry: pd.Timestamp,
               exit_session: pd.Timestamp) -> dict:
    series = frame.loc[frame.index >= entry, ["close", "adj_close"]]
    event = None
    if exit_session not in series.index and not series.empty:
        event = reader.terminal_event(entity_id, (entry - pd.Timedelta(days=1)).date().isoformat(),
                                      (exit_session + pd.Timedelta(days=10)).date().isoformat())
    return rules.exit_value(frame, entity_id, entry, exit_session, event)
