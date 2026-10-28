"""Closed categories of a failed job, with a message and a suggested action (#179).

The worker stores one of these codes; nothing here carries exception text, paths or credentials.
Codes stored before #179 (`job_failed`) read as an unclassified internal error.
"""

from typing import Literal

Retry = Literal["now", "later", "after_fix", "no"]

# code -> (category, label, message, action, when a new attempt makes sense)
FAILURES: dict[str, tuple[str, str, str, str, Retry]] = {
    "source_unavailable": (
        "source_unavailable", "Fuente no disponible",
        "Una fuente externa no respondió o devolvió un error del servidor (red, caída temporal o mantenimiento).",
        "Comprueba la conexión y reintenta más tarde.", "later"),
    "sources_failed": (
        "source_unavailable", "Fuentes no disponibles para algunos símbolos",
        "Fallaron fuentes externas para estos símbolos. El resto de los datos se actualizó.",
        "Reintenta más tarde; si se repite con los mismos símbolos, revisa su identidad en Calidad de los datos.",
        "later"),
    "key_missing": (
        "key_missing", "Falta una clave",
        "La fuente necesita una clave de acceso que no está guardada en este equipo.",
        "Guarda la clave en Administración → Claves y vuelve a intentarlo.", "after_fix"),
    "key_rejected": (
        "key_rejected", "Clave rechazada",
        "La fuente rechazó la clave guardada (no válida, caducada o sin permiso).",
        "Revisa o sustituye la clave en Administración → Claves y vuelve a intentarlo.", "after_fix"),
    "rate_limited": (
        "rate_limited", "Límite de peticiones",
        "La fuente limitó el número de peticiones (habitual en Yahoo y en las claves gratuitas).",
        "Espera al menos una hora antes de reintentar.", "later"),
    "insufficient_data": (
        "insufficient_data", "Datos insuficientes",
        "Los datos locales no bastan para este cálculo (sin precios, universo o histórico suficiente).",
        "Actualiza los datos o amplía el periodo y vuelve a lanzarlo.", "after_fix"),
    "worker_interrupted": (
        "interrupted", "Trabajo interrumpido",
        "El proceso que ejecutaba el trabajo se detuvo (cierre de GABI o del equipo).",
        "Reintenta cuando GABI vuelva a estar en marcha.", "now"),
    "internal_error": (
        "internal_error", "Error interno",
        "El trabajo falló por una causa no prevista en el código de GABI.",
        "Reintentar probablemente repetirá el fallo; revisa la traza local o comunícalo.", "no"),
    "job_failed": (
        "internal_error", "Causa no clasificada",
        "El trabajo falló antes de que GABI clasificara sus fallos; no se sabe si fue la red, una clave o el "
        "código.",
        "Reintenta una vez; si vuelve a fallar, la nueva tarjeta dirá la causa.", "now"),
}


def describe_failure(code: str | None, *, cancelled: bool = False) -> dict | None:
    """Category, label, message, action and retry advice of a failed or cancelled job."""
    if cancelled:
        return {"category": "cancelled", "label": "Cancelado", "message": "Se canceló a petición y no publicó un "
                "resultado.", "action": "Vuelve a lanzarlo cuando lo necesites.", "retry": "now"}
    category, label, message, action, retry = FAILURES.get(code or "", FAILURES["job_failed"])
    return {"category": category, "label": label, "message": message, "action": action, "retry": retry}
