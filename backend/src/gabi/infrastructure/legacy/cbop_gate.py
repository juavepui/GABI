"""Inputs of the CBOP-v1 data gate (#252): the reconstructed composition and the NYSE calendar."""

from datetime import date


def membership(as_of: str) -> dict:
    from gabi import universe

    return universe.get_sp500_constituents_asof(as_of)


def july_signals(first_year: int, last_year: int) -> list[date]:
    """The first NYSE session of July of each year: the signal after the 10-K season."""
    import exchange_calendars as xcals

    calendar = xcals.get_calendar("XNYS")
    return [calendar.date_to_session(f"{year}-07-01", direction="next").date()
            for year in range(first_year, last_year + 1)]
