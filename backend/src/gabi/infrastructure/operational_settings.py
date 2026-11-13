"""Versioned operational settings (#270, ADR 0008 point 4 and ADR 0009).

`config.py` stays as the sealed snapshot of the studies; the operational values
that used to be read from it are declared here, with a version, and nowhere else:

- the benchmark symbol is the active model's (``ModelVersion.benchmark_symbol``);
- how many hours cached fundamentals and SEC facts count as fresh;
- the Yahoo ``info`` fields kept in the fundamentals cache, including those the
  checklist (#167) added after `config.py` was sealed.

Declarative only: no I/O, read per operation. Changing a value is a commit that
declares a new version. ADR 0009 lets permanent flat modules import this module.
"""

from dataclasses import dataclass, replace

from gabi.infrastructure.model_versions import active_model


@dataclass(frozen=True)
class OperationalSettings:
    version: str
    cache_max_age_hours: int
    edgar_cache_max_age_hours: int
    info_keys: tuple[str, ...]


V1 = OperationalSettings(
    version="operational-settings-v1",
    cache_max_age_hours=24,
    # SEC annual and quarterly reports change far less often than prices or Yahoo's info.
    edgar_cache_max_age_hours=24 * 7,
    info_keys=(
        "shortName", "sector", "industry", "marketCap",
        "trailingPE", "forwardPE", "pegRatio", "priceToBook",
        "priceToSalesTrailing12Months", "enterpriseToEbitda",
        "returnOnEquity", "returnOnAssets", "operatingMargins",
        "grossMargins", "profitMargins", "debtToEquity", "currentRatio",
        "revenueGrowth", "earningsGrowth", "freeCashflow", "operatingCashflow",
        "trailingEps", "forwardEps", "beta",
        "fiftyTwoWeekHigh", "fiftyTwoWeekLow", "currentPrice", "regularMarketPrice",
        "trailingAnnualDividendYield", "averageDailyVolume3Month",
        # Corporate events calendar: Yahoo includes them in the same fundamentals fetch.
        "earningsTimestampStart", "earningsTimestampEnd", "isEarningsDateEstimate",
        "exDividendDate", "dividendDate",
        # Checklist (#167).
        "heldPercentInsiders",
    ),
)


# v2 (#245): Yahoo's enterpriseValue, to compare it with the SEC enterprise value of metrics V2.
V2 = replace(V1, version="operational-settings-v2", info_keys=(*V1.info_keys, "enterpriseValue"))


def current() -> OperationalSettings:
    return V2


def benchmark_symbol() -> str:
    """The active model's benchmark: the single source of what used to be ``config.BENCHMARK_SYMBOL``."""
    return active_model().benchmark_symbol
