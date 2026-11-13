"""Frozen hypothesis identity and visible model status over explicit weights."""

from collections.abc import Mapping
from types import MappingProxyType

MODES = ("INVESTOR", "RESEARCH")
DEFAULT_MODE = "INVESTOR"  # un usuario nuevo no debería aterrizar en herramientas de investigación


MODEL_STATUSES = ("FROZEN", "VALIDATED", "EXPERIMENTAL", "LIVE_FORWARD")

# La hipótesis exacta de HIPOTESIS_CONGELADA.md (2026-09-17). Si los pesos
# activos coinciden con esto, el modelo mostrado es el validado; si no, es
# una desviación experimental, se muestre donde se muestre -- no hay un
# término medio "casi congelado".
FROZEN_MODEL_ID = "GABI-MF-v1"
FROZEN_LABEL = "Hipótesis congelada 2026-09-17"
FROZEN_WEIGHTS = MappingProxyType({"value": 0.30, "quality": 0.35, "momentum": 0.25, "risk": 0.10})
FROZEN_WEIGHTS_TOLERANCE = 1e-6

def weights_match_frozen(weights: dict, tolerance: float = FROZEN_WEIGHTS_TOLERANCE, *, frozen_weights: Mapping[str, float] = FROZEN_WEIGHTS) -> bool:
    """True solo si los 4 pesos coinciden con FROZEN_WEIGHTS dentro de
    `tolerance` -- un peso ausente cuenta como 0.0 (no coincide), no se
    ignora la métrica."""
    if not weights:
        return False
    return all(abs(weights.get(k, 0.0) - v) <= tolerance for k, v in frozen_weights.items())


def model_status(weights: dict, *, live_forward_active: bool = False, frozen_weights: Mapping[str, float] = FROZEN_WEIGHTS) -> str:
    """FROZEN/VALIDATED/EXPERIMENTAL -- función pura (sin red, sin base de
    datos): `live_forward_active` lo decide el llamador (ver
    current_model_status para la versión que sí consulta las fuentes reales).

    - EXPERIMENTAL: `weights` se desvía de la hipótesis congelada, sea cual
      sea la magnitud.
    - LIVE_FORWARD: coincide con la hipótesis congelada Y hay seguimiento
      en vivo activo (una validación ciega bloqueada con rebalanceos reales,
      o al menos un experimento en fase LIVE_FORWARD).
    - FROZEN: coincide con la hipótesis congelada pero sin seguimiento
      en vivo activado todavía. Coincidir en pesos no acredita una ventaja
      independiente; VALIDATED queda reservado para una acreditación explícita.
      LIVE_FORWARD indica seguimiento, no éxito del estudio."""
    if not weights_match_frozen(weights, frozen_weights=frozen_weights):
        return "EXPERIMENTAL"
    return "LIVE_FORWARD" if live_forward_active else "FROZEN"


def experimental_banner_message(weights: dict, *, frozen_weights: Mapping[str, float] = FROZEN_WEIGHTS, frozen_label: str = FROZEN_LABEL) -> str | None:
    """Mensaje a mostrar cuando `weights` se desvía de la hipótesis
    congelada -- None si coincide (nada que avisar). El guardrail contra
    data snooping accidental: cambiar un peso siempre se ve, nunca es
    silencioso, y apunta a dónde registrar el experimento con trazabilidad."""
    if weights_match_frozen(weights, frozen_weights=frozen_weights):
        return None
    parts = ", ".join(f"{k.capitalize()} {v:.0%}" for k, v in weights.items())
    return (
        f"🧪 **EXPERIMENTAL** -- estos pesos ({parts}) no son los de la {frozen_label}. "
        "Este resultado no es una validación oficial del modelo. Si quieres conservar la "
        "trazabilidad de lo que pruebes, regístralo en Research Lab (Investigación, interfaz React)."
    )
