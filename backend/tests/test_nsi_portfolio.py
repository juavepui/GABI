"""NSI-v1 annual selection (#252): bands, division cap and no filling outside the bands."""

from gabi.domain.research import nsi_portfolio as rules


def universe(count: int) -> dict[str, float]:
    return {f"S{index:03d}": index / 1000 for index in range(count)}  # S000 has the lowest issuance.


def test_entries_come_from_the_lowest_quintile_in_issuance_order():
    values = universe(100)
    result = rules.select(values, {}, set(), top_n=20, max_per_division=50)
    assert result["selected"] == [f"S{index:03d}" for index in range(20)]
    small = rules.select(universe(50), {}, set(), top_n=20, max_per_division=50)
    assert len(small["selected"]) == 10  # Only the lowest quintile enters; the rest stays in cash.


def test_held_names_stay_within_the_hold_band_and_leave_beyond_it():
    values = universe(100)
    held = {"S035", "S039", "S045"}  # Percentiles 0.36, 0.40 and 0.46.
    result = rules.select(values, {}, held, top_n=20, max_per_division=50)
    assert result["kept"] == ["S035", "S039"] and result["dropped"] == ["S045"]
    assert result["selected"][:2] == ["S035", "S039"] and len(result["selected"]) == 20


def test_no_division_holds_more_than_six_names_and_unknown_sic_is_capped_too():
    values = universe(100)
    sics = {symbol: 2834 for symbol in values}  # Every issuer in division D.
    result = rules.select(values, sics, set())
    assert len(result["selected"]) == 6 and result["divisions"] == {"D": 6}
    assert result["capped_by_division"][0] == "S006"
    unknown = rules.select(values, {}, set())
    assert unknown["divisions"] == {"unknown": 6}
    assert rules.division(6021) == "H" and rules.division(9999) == "unknown" and rules.division(None) == "unknown"


def test_ties_break_by_symbol_and_percentiles_cover_the_ranked_universe():
    ranks = rules.percentiles({"B": 0.0, "A": 0.0, "C": -0.1})
    assert ranks == {"C": 1 / 3, "A": 2 / 3, "B": 1.0}
