"""Replay reviewed, dated index changes; never infer past members from today's list."""
import hashlib
import json
from datetime import date
from pathlib import Path

import pandas as pd

LEDGER_PATH = Path(__file__).with_name("resources") / "sp500_extension.json"


def reviewed_through() -> str:
    return str(json.loads(LEDGER_PATH.read_text(encoding="utf-8"))["verified_through"])


def symbols(value: str) -> set[str]:
    return {s.strip().replace(".", "-") for s in value.split(",") if s.strip()}


def fingerprint(members: set[str]) -> str:
    return hashlib.sha256(",".join(sorted(members)).encode()).hexdigest()


def extend_membership(history: pd.DataFrame, ledger: dict) -> pd.DataFrame:
    """Validate the anchor, replay effective dates and reconcile the observed endpoint.

    Existing rows must agree throughout the extension. Original rows are retained;
    the endpoint is a dated observation, not an invented index change.
    """
    anchor = ledger["anchor_date"]
    through = ledger["verified_through"]
    if date.fromisoformat(through) > date.today() or through <= anchor:
        raise ValueError("Invalid membership verification interval")
    history = history.sort_values("date", kind="stable").reset_index(drop=True)
    if history.loc[history["date"] >= anchor, "date"].duplicated().any():
        raise ValueError("Duplicate membership dates")
    base = history[history["date"] == anchor]
    if len(base) != 1:
        raise ValueError("Reviewed membership anchor is missing")
    members = symbols(str(base.iloc[0]["tickers"]))
    if fingerprint(members) != ledger["anchor_sha256"]:
        raise ValueError("Reviewed membership anchor has changed")
    events = pd.DataFrame(ledger["events"])
    rows = []
    for effective, group in events.groupby("effective_date", sort=True):
        date.fromisoformat(effective)
        if not anchor < effective <= through:
            raise ValueError("Event outside reviewed interval")
        for event in group.to_dict("records"):
            if not event["source_url"].startswith("https://"):
                raise ValueError("Missing event source")
            removed, added = event["removed"], event["added"]
            if not removed and not added:
                raise ValueError("Empty event")
            if removed:
                if removed not in members:
                    raise ValueError(f"{effective}: cannot remove absent member {removed}")
                members.remove(removed)
            if added:
                if added in members:
                    raise ValueError(f"{effective}: duplicate addition {added}")
                members.add(added)
        rows.append({"date": effective, "tickers": ",".join(sorted(members))})
    if members != set(ledger["endpoint_symbols"]):
        raise ValueError("Reconstructed index does not match observed endpoint")
    if not rows or rows[-1]["date"] != through:
        rows.append({"date": through, "tickers": ",".join(sorted(members))})
    extension = pd.DataFrame(rows)
    for row in history[(history["date"] > anchor) & (history["date"] <= through)].itertuples():
        previous = extension[extension["date"] <= row.date]
        expected = symbols(str(previous.iloc[-1]["tickers"])) if not previous.empty else symbols(str(base.iloc[0]["tickers"]))
        if symbols(str(row.tickers)) != expected:
            raise ValueError(f"Existing membership conflicts with reviewed events at {row.date}")
    missing = extension[~extension["date"].isin(history["date"])]
    return pd.concat([history, missing], ignore_index=True).sort_values("date", kind="stable").reset_index(drop=True)


def apply_reviewed_extension(history: pd.DataFrame) -> pd.DataFrame:
    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    # Independent custom/test histories can use another anchor.
    if ledger["anchor_date"] not in set(history["date"]):
        return history
    return extend_membership(history, ledger)
