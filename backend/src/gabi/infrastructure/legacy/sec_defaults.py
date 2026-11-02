"""Read-only compatibility setting from the versioned operational settings (#270); never mutates `config`."""

from gabi.infrastructure import operational_settings


def cache_max_age_hours() -> int:
    return operational_settings.current().edgar_cache_max_age_hours
