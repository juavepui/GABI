"""Modo global de la app (INVESTOR/RESEARCH) y estado del modelo activo
(FROZEN/VALIDATED/EXPERIMENTAL/LIVE_FORWARD).

La lógica vive aquí, no repartida por páginas de Streamlit -- para que sea
testeable sin navegador (criterio de aceptación explícito de este objetivo)
y para que decidir qué es INVESTOR/RESEARCH o qué cuenta como desviación
experimental no dependa de "ocultar un widget" en cada página por separado.

INVESTOR: navegación reducida a USAR la hipótesis congelada -- oportunidades
(Screener), ficha, cambios materiales (Signal Monitor), cartera, diario y
calidad/confianza de los datos. Los pesos del score quedan bloqueados a la
hipótesis congelada: no hay sliders que tocar por accidente.

RESEARCH: acceso completo, incluida la experimentación (Ranking histórico,
Factor Lab, Research Lab, Blind Forward Validation y Portfolio Lab en React). Calidad
sigue permitiendo experimentar, pero cualquier desviación de los pesos
congelados queda marcada EXPERIMENTAL de forma visible, nunca silenciosa."""
import json

from gabi.domain.market import model_policy as _policy

from . import config

MODES = _policy.MODES
DEFAULT_MODE = _policy.DEFAULT_MODE
MODE_PATH = config.DATA_DIR / "app_mode.json"
MODEL_STATUSES = _policy.MODEL_STATUSES
FROZEN_MODEL_ID = _policy.FROZEN_MODEL_ID
FROZEN_LABEL = _policy.FROZEN_LABEL
FROZEN_WEIGHTS = dict(_policy.FROZEN_WEIGHTS)
FROZEN_WEIGHTS_TOLERANCE = _policy.FROZEN_WEIGHTS_TOLERANCE


def get_mode() -> str:
    """Persistido en disco (no solo session_state de Streamlit) para que un
    usuario junior no tenga que volver a elegir INVESTOR cada vez que abre
    la app -- mismo patrón que config.load_weights()."""
    if MODE_PATH.exists():
        try:
            saved = json.loads(MODE_PATH.read_text()).get("mode")
            if saved in MODES:
                return saved
        except (OSError, ValueError):
            pass
    return DEFAULT_MODE


def set_mode(mode: str):
    if mode not in MODES:
        raise ValueError(f"mode debe ser uno de {MODES}")
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    MODE_PATH.write_text(json.dumps({"mode": mode}))


def weights_match_frozen(weights: dict, tolerance: float = FROZEN_WEIGHTS_TOLERANCE) -> bool:
    return _policy.weights_match_frozen(weights, tolerance, frozen_weights=FROZEN_WEIGHTS)


def model_status(weights: dict, *, live_forward_active: bool = False) -> str:
    return _policy.model_status(weights, live_forward_active=live_forward_active, frozen_weights=FROZEN_WEIGHTS)


def _research_lab_live_forward_active() -> bool:
    """Señal débil de seguimiento en vivo: algún experimento marcado
    LIVE_FORWARD en Research Lab -- no garantiza que corresponda a una
    validación ciega real en marcha, cualquiera puede registrar un
    experimento con ese `stage` a mano sin más disciplina detrás."""
    from . import research_lab  # import diferido: no acopla este módulo a research_lab/storage en import time
    try:
        return not research_lab.list_experiments(stage="LIVE_FORWARD").empty
    except Exception:
        return False  # el estado del modelo no debe romperse porque falle una consulta secundaria


def _blind_validation_live_forward_id(weights: dict) -> int | None:
    """Señal fuerte de seguimiento en vivo: el id de una validación ciega
    BLOQUEADA (`status == "locked"`, no rota antes de tiempo con
    break_seal_early), con los pesos exactos de la hipótesis congelada y al
    menos un rebalanceo real ya registrado -- blind_validation.py es la
    disciplina genuina contra ajustar la estrategia a medio camino, así que
    es la señal que de verdad debería encender LIVE_FORWARD, no una
    etiqueta suelta de Research Lab. None si no hay ninguna así; nunca
    lanza si la consulta falla (misma cautela que la señal débil)."""
    from . import blind_validation  # import diferido, mismo motivo que research_lab arriba
    try:
        validations = blind_validation.list_validations()
        for _, row in validations.iterrows():
            if row["status"] != "locked":
                continue
            try:
                row_weights = json.loads(row["weights_json"])
            except (TypeError, ValueError):
                continue
            if not weights_match_frozen(row_weights):
                continue
            if blind_validation.get_status(int(row["id"]))["n_periods"] >= 1:
                return int(row["id"])
    except Exception:
        pass
    return None


def current_model_status() -> dict:
    """Envoltorio NO puro sobre model_status()/weights_match_frozen(): lee
    los pesos guardados (config.load_weights) y combina las dos señales de
    seguimiento en vivo -- una validación ciega real bloqueada (señal
    fuerte, ver _blind_validation_live_forward_id) o un experimento
    LIVE_FORWARD suelto en Research Lab (señal débil) -- para que la UI
    solo tenga que llamar a esto una vez, sin repetir la lógica de qué
    cuenta como FROZEN/EXPERIMENTAL en cada página.

    `live_forward_source`/`blind_validation_id` exponen CUÁL de las dos
    señales encendió LIVE_FORWARD, para que la UI pueda enlazar a la
    validación concreta en vez de mostrar un estado sin trazabilidad."""
    weights = config.load_weights()
    blind_validation_id = _blind_validation_live_forward_id(weights)
    live_forward_active = blind_validation_id is not None or _research_lab_live_forward_active()
    matches = weights_match_frozen(weights)
    return {
        "status": model_status(weights, live_forward_active=live_forward_active),
        "weights": weights,
        "model_id": FROZEN_MODEL_ID if matches else "EXPERIMENTAL",
        "matches_frozen": matches,
        "live_forward_source": ("blind_validation" if blind_validation_id is not None
                                else "research_lab" if live_forward_active else None),
        "blind_validation_id": blind_validation_id,
    }


def experimental_banner_message(weights: dict) -> str | None:
    return _policy.experimental_banner_message(weights, frozen_weights=FROZEN_WEIGHTS, frozen_label=FROZEN_LABEL)
