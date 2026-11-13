"""Descriptive sector and industry concentration of a target portfolio (#180).

It never changes the selection: limiting sectors would be a strategy change (#60).
"""

import pandas as pd

SECTOR_LIMIT_PCT = 25.0
INDUSTRY_LIMIT_PCT = 15.0
UNKNOWN_SECTOR = "Sin sector"


def _labels(values: pd.Series, missing: str | None) -> pd.Series:
    text = values.astype("string").str.strip()
    return text.mask(text.isna() | (text == ""), missing)


def sector_breakdown(target: pd.DataFrame, universe: pd.DataFrame) -> list[dict]:
    """Weight of each sector in the target against its share of the universe's total market capitalisation.

    Every sector of either side is listed, so an absent sector shows its underweight."""
    sectors = _labels(target.get("sector", pd.Series(index=target.index, dtype="string")), UNKNOWN_SECTOR)
    weights = target["weight_pct"].astype(float).groupby(sectors).sum()
    positions = sectors.value_counts()
    caps = pd.to_numeric(universe.get("market_cap", pd.Series(index=universe.index, dtype=float)), errors="coerce")
    caps = caps[caps > 0]
    index: pd.Series = pd.Series(dtype=float)
    if not caps.empty:
        universe_sectors = _labels(universe.loc[caps.index].get(
            "sector", pd.Series(index=caps.index, dtype="string")), UNKNOWN_SECTOR)
        index = caps.groupby(universe_sectors).sum() / caps.sum() * 100
    rows = []
    for sector in sorted(set(weights.index) | set(index.index)):
        weight = float(weights.get(sector, 0.0))
        benchmark = float(index[sector]) if sector in index.index else (0.0 if not index.empty else None)
        rows.append({"sector": str(sector), "positions": int(positions.get(sector, 0)), "weight_pct": weight,
                     "index_weight_pct": benchmark,
                     "difference_pp": None if benchmark is None else weight - benchmark})
    return sorted(rows, key=lambda row: (-row["weight_pct"], -(row["index_weight_pct"] or 0), row["sector"]))


def industry_breakdown(target: pd.DataFrame, industries: dict[str, str]) -> list[dict]:
    """Weight of each industry held; positions without a known industry are left out."""
    frame = pd.DataFrame({
        "industry": _labels(pd.Series([industries.get(str(symbol)) for symbol in target.index], index=target.index,
                                      dtype="string"), None),
        "sector": _labels(target.get("sector", pd.Series(index=target.index, dtype="string")), UNKNOWN_SECTOR),
        "weight_pct": target["weight_pct"].astype(float)}).dropna(subset=["industry"])
    rows = [{"industry": str(industry), "sector": str(group["sector"].mode().iloc[0]), "positions": len(group),
             "weight_pct": float(group["weight_pct"].sum())} for industry, group in frame.groupby("industry")]
    return sorted(rows, key=lambda row: (-row["weight_pct"], row["industry"]))


def concentration_warnings(sectors: list[dict], industries: list[dict], *, sector_limit_pct: float = SECTOR_LIMIT_PCT,
                           industry_limit_pct: float = INDUSTRY_LIMIT_PCT) -> list[dict]:
    """Sectors and industries whose weight exceeds its limit, heaviest first."""
    found = [{"kind": "sector", "name": row["sector"], "positions": row["positions"], "weight_pct": row["weight_pct"],
              "limit_pct": sector_limit_pct} for row in sectors if row["weight_pct"] > sector_limit_pct + 1e-9]
    found += [{"kind": "industry", "name": row["industry"], "positions": row["positions"],
               "weight_pct": row["weight_pct"], "limit_pct": industry_limit_pct}
              for row in industries if row["weight_pct"] > industry_limit_pct + 1e-9]
    return sorted(found, key=lambda row: -row["weight_pct"])
