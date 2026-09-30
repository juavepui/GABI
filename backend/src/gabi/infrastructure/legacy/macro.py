"""Static published FRED labels and units, without running an update."""

from gabi import macro


def series_metadata() -> dict[str, dict]:
    return {key: {field: value[field] for field in ("label", "unit", "help")}
            for key, value in macro.SERIES.items()}
