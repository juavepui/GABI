"""Research context of one company that the old Ficha showed next to its score; none of it is scored."""

import re
from collections.abc import Callable
from datetime import date
from typing import Protocol

import pandas as pd

from gabi.application.errors import QueryError
from gabi.application.research.historical import _json_value

SYMBOL = re.compile(r"[A-Z0-9^][A-Z0-9^-]{0,19}\Z")
DATASETS = ("surprises", "estimates", "insiders")
INSIDER_MONTHS = 6
MAX_INSIDER_SHOWN = 200
INSIDER_KEYS = ("transaction_date", "owner_name", "owner_title", "transaction_code", "shares",
                "price_per_share", "is_10b5_1_plan", "filed_date")
SURPRISE_KEYS = ("earnings_date", "eps_estimate", "eps_reported", "surprise_pct", "price_reaction_pct")
ESTIMATE_KEYS = ("captured_at", "eps_avg", "eps_low", "eps_high", "eps_analysts", "eps_dispersion_pct",
                 "revised_up_30d", "revised_down_30d", "source")


class ResearchStore(Protocol):
    def surprises(self, symbol: str) -> pd.DataFrame: ...
    def estimate_history(self, symbol: str, period: str) -> pd.DataFrame: ...
    def insider_transactions(self, symbol: str) -> pd.DataFrame: ...
    def insider_fetched_at(self, symbol: str) -> str | None: ...


class CompanyMath(Protocol):
    def revision(self, history: pd.DataFrame, lookback_days: int, as_of: date) -> dict | None: ...
    def insiders(self, symbol: str, transactions: pd.DataFrame, months: int, as_of: date) -> dict: ...
    def transaction_labels(self) -> dict[str, str]: ...


def normalize_symbol(symbol: str) -> str:
    normalized = (symbol or "").strip().upper().replace(".", "-")
    if not SYMBOL.fullmatch(normalized):
        raise QueryError("invalid_symbol", "Indica un símbolo válido.", 422)
    return normalized


def normalize_company_sync(options: dict | None) -> dict:
    options = options or {}
    if set(options) != {"symbol", "dataset"} or options.get("dataset") not in DATASETS:
        raise QueryError("invalid_job", "Indica una empresa y qué sincronizar (sorpresas o estimaciones).", 422)
    return {"symbol": normalize_symbol(str(options["symbol"])), "dataset": options["dataset"]}


def _row(values: dict, keys: tuple[str, ...]) -> dict:
    return {key: _json_value(values.get(key)) for key in keys}


class CompanyResearch:
    def __init__(self, store: ResearchStore, events: Callable[[str, date], list[dict]],
                 filings: Callable[[str], list[dict]], math: CompanyMath, today: Callable[[], date]):
        self.store, self.events, self.filings, self.math, self.today = store, events, filings, math, today

    def overview(self, symbol: str) -> dict:
        """Upcoming dated events, the surprise history and the latest consensus capture (current quarter)."""
        symbol = normalize_symbol(symbol)
        today = self.today()
        upcoming = sorted((event for event in self.events(symbol, today) if event["days_until"] >= 0),
                          key=lambda event: event["event_date"])
        history = self.store.estimate_history(symbol, "0q")
        latest = history.iloc[-1].to_dict() if not history.empty else None
        revision = self.math.revision(history, 90, today) if not history.empty else None
        return {
            "symbol": symbol,
            "events": [{key: _json_value(event[key]) for key in ("event_type", "event_date", "range_end",
                                                                 "is_estimate", "days_until", "source")}
                       for event in upcoming],
            "surprises": [_row(row, SURPRISE_KEYS) for row in self.store.surprises(symbol).to_dict("records")],
            "estimate": None if latest is None else _row(latest, ESTIMATE_KEYS),
            "revision_90d": None if revision is None else {key: _json_value(value) for key, value in revision.items()},
        }

    def insiders(self, symbol: str) -> dict:
        """The old Ficha «Actividad de insiders (SEC Form 4)»: six-month open-market summary and recent lines."""
        symbol = normalize_symbol(symbol)
        summary = self.math.insiders(symbol, self.store.insider_transactions(symbol), INSIDER_MONTHS, self.today())
        recent = summary["recent"]
        labels = self.math.transaction_labels()
        rows = [_row(row, INSIDER_KEYS) | {"transaction_label": labels.get(row["transaction_code"],
                                                                            row["transaction_code"])}
                for row in recent.head(MAX_INSIDER_SHOWN).to_dict("records")]
        return {"symbol": symbol, "months": INSIDER_MONTHS, "fetched_at": self.store.insider_fetched_at(symbol),
                "n_buys": summary["n_buys"], "n_sells": summary["n_sells"],
                "distinct_buyers": summary["distinct_buyers"], "distinct_sellers": summary["distinct_sellers"],
                "net_value": _json_value(summary["net_value"]),
                "has_10b5_1_only_buys": summary["has_10b5_1_only_buys"],
                "recent": rows, "recent_total": int(len(recent))}

    def filing_changes(self, symbol: str) -> dict:
        """Latest 10-K and 10-Q against the previous comparable filing, from cached SEC facts."""
        symbol = normalize_symbol(symbol)
        results = []
        for result in self.filings(symbol):
            results.append({
                "form": result["form"], "reason": result["reason"],
                "current": None if result["current"] is None else {
                    key: _json_value(result["current"].get(key)) for key in ("filed_date", "period_end", "url")},
                "previous": None if result["previous"] is None else {
                    key: _json_value(result["previous"].get(key)) for key in ("filed_date", "period_end", "url")},
                "rows": [{key: _json_value(value) for key, value in row.items()} for row in result["rows"]],
            })
        return {"symbol": symbol, "results": results}
