"""Periods of the accredited historical layer (#26-#28 for 2010-2015, #34 for 2016-2025).

Each period keeps its own membership source, SEC identity-interval source and
price-audit producer, so rebuilding one period never replaces the evidence of
the other. The 2010-2015 identifiers are the ones already stored and cited in
the frozen #33 validation; they must not change.
"""

from dataclasses import dataclass
from datetime import date, timedelta

# fja05680 at the pinned commit; imported only up to 2016 in #26.
REFERENCE_SOURCE = "fja05680:a2430f2af0c79ddf0748e91de11bdeb1616ab5a7"
# The same pinned file imported over its full coverage (1996-01-02 .. 2026-08-18).
REFERENCE_SOURCE_FULL = "fja05680:a2430f2af0c79ddf0748e91de11bdeb1616ab5a7:full"


@dataclass(frozen=True)
class Period:
    key: str
    start: str  # first covered day (inclusive)
    end_exclusive: str
    membership_source: str
    identity_source: str
    price_producer: str
    # Prices are read from ``series_start`` (trailing window before the first
    # rebalance) through ``series_end`` (holding after the last rebalance).
    series_start: str
    series_end: str
    # #34: try the CIK's current SEC ticker when the index label is no longer
    # its symbol (Yahoo keeps an issuer's history under today's ticker).
    price_symbol_fallback: bool = False
    # SEC periodic reports visible to a nomination's evidence window may start
    # this many days before the period (early-2016 index exits, #34).
    evidence_margin_days: int = 0
    # Evidence horizon of the price audit: SEC frames through this year, the
    # "no later public float" delisting rule before this date, and the last
    # archive date per source (None: all local data).
    frame_year_max: int | None = None
    floatless_before: str = "2025-01-01"
    archive_last: tuple[tuple[str, str], ...] = ()

    def archive_until(self, source: str) -> str:
        return dict(self.archive_last).get(source, self.series_end)

    @property
    def life_horizon(self) -> tuple[str, int | None]:
        return self.floatless_before, self.frame_year_max

    @property
    def last_day(self) -> str:
        return (date.fromisoformat(self.end_exclusive) - timedelta(days=1)).isoformat()

    @property
    def years(self) -> range:
        return range(int(self.start[:4]), int(self.end_exclusive[:4]))

    @property
    def quarters(self) -> list[str]:
        return [date(year, month, day).isoformat() for year in self.years
                for month, day in ((3, 31), (6, 30), (9, 30), (12, 31))]

    @property
    def evidence_from(self) -> str:
        return (date.fromisoformat(self.start) - timedelta(days=self.evidence_margin_days)).isoformat()

    @property
    def slug(self) -> str:
        return self.key.replace("-", "_")

    def covers(self, day: str) -> bool:
        return self.start <= day[:10] < self.end_exclusive


P2010 = Period(key="2010-2015", start="2010-01-01", end_exclusive="2016-01-01",
               membership_source=REFERENCE_SOURCE,
               identity_source="sec-identity-evidence:2010-2015:v1",
               price_producer="historical_price_audit:v2",
               series_start="2008-01-01", series_end="2016-06-30",
               # As audited in #28: FINSABER imported through 2015, frames through
               # CY2016, floatless delistings only before 2016.
               frame_year_max=2016, floatless_before="2016-01-01",
               archive_last=(("finsaber", "2015-12-31"),))
P2016 = Period(key="2016-2025", start="2016-01-01", end_exclusive="2026-01-01",
               membership_source=REFERENCE_SOURCE_FULL,
               identity_source="sec-identity-evidence:2016-2025:v1",
               price_producer="historical_price_audit:v2:2016-2025",
               series_start="2014-01-01", series_end="2026-06-30", price_symbol_fallback=True,
               evidence_margin_days=400)
PERIODS = {period.key: period for period in (P2010, P2016)}


def get(key: str) -> Period:
    try:
        return PERIODS[key]
    except KeyError:
        raise ValueError(f"Unknown historical period: {key}") from None


def for_date(day: str) -> Period | None:
    return next((period for period in PERIODS.values() if period.covers(day)), None)
