"""Published SEC refresh eligibility; no download or historical identity inference."""

from datetime import datetime

MISSING_CIK = ("Símbolo no encontrado en el mapeo ticker→CIK de la SEC (ni en vivo ni en "
               "resoluciones anteriores) — posible ticker deslistado hace tiempo, o nunca resuelto antes")
MISSING_HISTORICAL_CIK = "Identidad/CIK histórico sin acreditar para esta fecha"


def stale_symbols(symbols: list[str], fetched_at: dict, covered: set[str], failed: set[str],
                  now: datetime, max_age_hours: int, *, force: bool, full_refresh: bool) -> list[str]:
    return [symbol for symbol in symbols
            if force or full_refresh or symbol in failed or fetched_at.get(symbol) is None
            or (now - fetched_at[symbol]).total_seconds() > max_age_hours * 3600 or symbol not in covered]
