"""Annual NSI-v1 selection (#252), exactly as preregistered in ``docs/research/nsi-v1/preregistro.json``.

Lower issuance is better. Members with an issuance value are ranked by it
(ascending; ties by symbol) and given a percentile in (0, 1]. A held name stays
while its percentile is within the hold band (40 %); new names enter only from the
entry band (lowest quintile). Held names are kept first, by issuance; then entries
fill up to ``top_n``. No SIC division may hold more than ``max_per_division``
names; an issuer without a known SIC forms its own ``unknown`` group, capped the
same way. Positions left empty stay in cash: nothing is filled from outside the
bands.
"""

from collections.abc import Mapping

DIVISIONS = {"A": (100, 999), "B": (1000, 1499), "C": (1500, 1799), "D": (2000, 3999), "E": (4000, 4999),
             "F": (5000, 5199), "G": (5200, 5999), "H": (6000, 6799), "I": (7000, 8999), "J": (9100, 9799)}
ENTER_BAND = 0.20
HOLD_BAND = 0.40
TOP_N = 20
MAX_PER_DIVISION = 6


def division(sic: int | None) -> str:
    if sic is None:
        return "unknown"
    return next((name for name, (low, high) in DIVISIONS.items() if low <= sic <= high), "unknown")


def percentiles(values: Mapping[str, float]) -> dict[str, float]:
    ordered = sorted(values, key=lambda symbol: (values[symbol], symbol))
    return {symbol: (index + 1) / len(ordered) for index, symbol in enumerate(ordered)}


def select(values: Mapping[str, float], sics: Mapping[str, int | None], held: set[str], *, top_n: int = TOP_N,
           max_per_division: int = MAX_PER_DIVISION, enter: float = ENTER_BAND, hold: float = HOLD_BAND) -> dict:
    ranks = percentiles(values)
    order = sorted(ranks, key=lambda symbol: (ranks[symbol], symbol))
    kept = [symbol for symbol in order if symbol in held and ranks[symbol] <= hold]
    entries = [symbol for symbol in order if symbol not in held and ranks[symbol] <= enter]
    chosen: list[str] = []
    counts: dict[str, int] = {}
    capped: list[str] = []
    for symbol in kept + entries:
        if len(chosen) >= top_n:
            break
        group = division(sics.get(symbol))
        if counts.get(group, 0) >= max_per_division:
            capped.append(symbol)
            continue
        counts[group] = counts.get(group, 0) + 1
        chosen.append(symbol)
    return {"selected": chosen, "kept": [symbol for symbol in chosen if symbol in held],
            "dropped": sorted(held - set(chosen)), "capped_by_division": capped, "divisions": counts,
            "ranked": len(values)}
