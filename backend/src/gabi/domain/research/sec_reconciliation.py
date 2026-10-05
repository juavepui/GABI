"""Reconcile SEC NUM values with exact issuer facts, retaining unmatched evidence."""
import numpy as np
import pandas as pd

NOTES = ("NUM dates/quarters rounded only for reconciliation; original dates retained in exact facts. "
         "Values may be reported more than once in an accession.")


def rounded_periods(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    end = pd.to_datetime(frame.end_date)
    previous = end - pd.offsets.MonthEnd(1)
    following = end + pd.offsets.MonthEnd(0)
    # SEC NUM uses the preceding reporting month for days 1-15. February
    # 14/15 contexts in Costco/AutoZone establish that this is not geometric
    # distance to calendar month-end. Exact dates stay unchanged.
    closest = following.where(end.dt.day > 15, previous)
    frame["end_month"] = closest.dt.strftime("%Y-%m-%d")
    start = pd.to_datetime(frame.start_date.replace("", None))
    frame["qtrs"] = ((end - start).dt.days / 91.25).round().fillna(0).astype(int)
    return frame


def compare(bulk: pd.DataFrame, exact: pd.DataFrame) -> pd.DataFrame:
    keys = ["cik", "accn", "tag", "end_month", "qtrs", "unit"]
    exact = rounded_periods(exact)
    indexed = bulk.reset_index(drop=True).reset_index(names="row_id")
    joined = indexed.merge(exact[keys + ["val"]].drop_duplicates(), on=keys, how="left", suffixes=("_bulk", "_exact"))
    joined["has_exact"] = joined.val_exact.notna()
    # NUM retains four decimals; never scale the tolerance with dollar amounts.
    joined["matches"] = np.isclose(joined.val_bulk, joined.val_exact, rtol=0, atol=0.0001)
    grouped = joined.groupby("row_id")[["has_exact", "matches"]].any()
    indexed["comparison"] = np.where(grouped.matches, "matches", np.where(grouped.has_exact, "different_value", "no_exact_context"))
    return indexed.drop(columns="row_id")


def summary(result: pd.DataFrame) -> dict:
    return {"bulk_facts": len(result), "comparison": result.comparison.value_counts().to_dict(), "notes": NOTES}
