"""Interpret stored SEC facts without storage, clock or ticker resolution."""

import pandas as pd


def issuer_versions(frame: pd.DataFrame, cik: str, tags: list[str] | None = None) -> pd.DataFrame:
    if frame.empty:
        return frame
    frame = frame[frame["form"].isin(["10-K", "10-Q", "10-K/A", "10-Q/A"])].copy()
    if tags:
        frame = frame[frame["tag"].isin(tags)].copy()
    frame["cik"] = cik
    return frame.sort_values(["filed_date", "end_date", "accn", "tag"], kind="stable").reset_index(drop=True)


def value_as_of(frame: pd.DataFrame, as_of: str, unit: str = "USD") -> float | None:
    if frame.empty:
        return None
    frame = frame[(frame["unit"] == unit) & frame["filed_date"].notna() & (frame["filed_date"] <= as_of)]
    if frame.empty:
        return None
    # Preserve the published ordering across tags; callers supply the tag set.
    return float(frame.sort_values(["filed_date", "end_date"]).iloc[-1]["val"])


def companyfacts(frame: pd.DataFrame, as_of: str | None = None) -> dict:
    if frame.empty:
        return {"facts": {"us-gaap": {}}}
    if as_of:
        frame = frame[frame["filed_date"].notna() & (frame["filed_date"] <= as_of)]
    families = {}
    for tag, group in frame.groupby("tag"):
        units = {}
        for unit, rows in group.groupby("unit"):
            units[unit] = [{"start": row.start_date or None, "end": row.end_date, "val": row.val,
                            "form": row.form, "fp": row.fp, "fy": row.fy, "filed": row.filed_date,
                            "accn": row.accn} for row in rows.itertuples()]
        families[tag] = {"units": units}
    return {"facts": {"us-gaap": families}}
