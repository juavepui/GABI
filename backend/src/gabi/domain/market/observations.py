"""Observation-key revision policy shared by source synchronizers."""

import pandas as pd


def delta_rows(old: pd.DataFrame, new: pd.DataFrame) -> tuple[pd.DataFrame, int, int]:
    """Same observation key changed => revised; unseen key => new. NaNs equal."""
    if new.index.has_duplicates:
        raise ValueError("Observaciones duplicadas en la respuesta.")
    fresh = ~new.index.isin(old.index)
    aligned = old.reindex(index=new.index, columns=new.columns)
    equal = new.eq(aligned) | (new.isna() & aligned.isna())
    changed = ~equal.all(axis=1) & ~fresh
    return new.loc[fresh | changed], int(fresh.sum()), int(changed.sum())


def change_status(new: int, revised: int) -> str:
    # Counts preserve mixed outcomes; revised takes precedence over new.
    return "revised" if revised else "new" if new else "unchanged"
