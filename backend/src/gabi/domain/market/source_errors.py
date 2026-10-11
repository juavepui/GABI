"""Classify source failures from their message and size bounded retry waits; no network types."""

RETRYABLE_CATEGORIES = frozenset({"rate_limit", "timeout", "connection"})
MAX_RETRY_WAIT_SECONDS = 30.


def classify(message: str, service: str = "Yahoo Finance") -> tuple[str, str]:
    """(category, Spanish reason) shared by every source adapter."""
    lower = message.lower()
    if "429" in message or "too many requests" in lower or "rate limit" in lower:
        return "rate_limit", f"Límite de peticiones de {service} alcanzado (rate limit)"
    if "delisted" in lower or "no data found" in lower or "no price data" in lower or "not found" in lower:
        return "not_found", "Sin datos disponibles (ticker posiblemente deslistado, incorrecto o sin cobertura)"
    if "timeout" in lower or "timed out" in lower:
        return "timeout", f"Tiempo de espera agotado al contactar con {service}"
    if "connection" in lower or "connect" in lower or "network" in lower or "resolve" in lower:
        return "connection", f"Error de conexión de red con {service}"
    if "json" in lower or "expecting value" in lower:
        return "invalid_response", "Respuesta inválida o vacía del servidor"
    return "other", (message[:200] if message else "Error desconocido")


def retry_wait(attempt_index: int, *, has_response: bool, retry_after: object = None) -> float:
    """Exponential wait, raised to a numeric Retry-After, bounded so a failed run stays resumable."""
    delay = min(MAX_RETRY_WAIT_SECONDS, 1.5 * 2 ** attempt_index)
    if has_response:
        try:
            requested = delay if retry_after is None else float(retry_after)  # type: ignore[arg-type]
            delay = min(MAX_RETRY_WAIT_SECONDS, max(delay, requested))
        except ValueError:
            pass
    return delay
