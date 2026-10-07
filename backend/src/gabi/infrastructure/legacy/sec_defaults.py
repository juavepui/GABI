"""Read-only compatibility setting; never mutates the frozen configuration."""

from gabi import config


def cache_max_age_hours() -> int:
    return config.EDGAR_CACHE_MAX_AGE_HOURS
