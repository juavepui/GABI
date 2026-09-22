"""Modo global de la app (INVESTOR/RESEARCH) y estado del modelo activo
(FROZEN/VALIDATED/EXPERIMENTAL/LIVE_FORWARD).

La lógica vive aquí, no repartida por páginas de Streamlit -- para que sea
testeable sin navegador (criterio de aceptación explícito de este objetivo)
y para que decidir qué es INVESTOR/RESEARCH o qué cuenta como desviación
experimental no dependa de "ocultar un widget" en cada página por separado.

INVESTOR: navegación reducida a USAR el modelo ya validado -- oportunidades
(Screener), ficha, cambios materiales (Signal Monitor), cartera, diario y
calidad/confianza de los datos. Los pesos del score quedan bloqueados a la
hipótesis congelada: no hay sliders que tocar por accidente.

RESEARCH: acceso completo, incluida la experimentación (Ranking histórico,
Research Lab, Factor Lab, Blind Forward Validation, Portfolio Lab). Calidad
sigue permitiendo experimentar, pero cualquier desviación de los pesos
congelados queda marcada EXPERIMENTAL de forma visible, nunca silenciosa."""
import json

from . import config

MODES = ("INVESTOR", "RESEARCH")
DEFAULT_MODE = "INVESTOR"  # un usuario nuevo no debería aterrizar en herramientas de investigación

MODE_PATH = config.DATA_DIR / "app_mode.json"

MODEL_STATUSES = ("FROZEN", "VALIDATED", "EXPERIMENTAL", "LIVE_FORWARD")

# La hipótesis exacta de HIPOTESIS_CONGELADA.md (2026-09-17). Si los pesos
# activos coinciden con esto, el modelo mostrado es el validado; si no, es
# una desviación experimental, se muestre donde se muestre -- no hay un
# término medio "casi congelado".
FROZEN_MODEL_ID = "GABI-MF-v1"
FROZEN_LABEL = "Hipótesis congelada 2026-09-17"
FROZEN_WEIGHTS = {"value": 0.30, "quality": 0.35, "momentum": 0.25, "risk": 0.10}
FROZEN_WEIGHTS_TOLERANCE = 1e-6

# Páginas visibles en modo INVESTOR (ruta tal cual la registra
# streamlit_app.py). No es una lista de "páginas peligrosas que se
# esconden": es la lista explícita y positiva de lo que hace falta para
# USAR el modelo -- todo lo demás (herramientas de investigación) queda
# solo en RESEARCH.
INVESTOR_PAGES = frozenset({
    "pages/7_Aprender.py",
    "pages/1_Screener.py",
    "pages/2_Ficha_Empresa.py",
    "pages/6_Comparar_Empresas.py",
    "pages/16_Signal_Monitor.py",
    "pages/9_Decisiones.py",
    "pages/10_Carteras_Simuladas.py",
    "pages/4_Diario_Inversion.py",
    "pages/15_Salud_Datos.py",
    "pages/5_Panel_Macro.py",
    "pages/3_Configuracion.py",
})


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
    """True solo si los 4 pesos coinciden con FROZEN_WEIGHTS dentro de
    `tolerance` -- un peso ausente cuenta como 0.0 (no coincide), no se
    ignora la métrica."""
    if not weights:
        return False
    return all(abs(weights.get(k, 0.0) - v) <= tolerance for k, v in FROZEN_WEIGHTS.items())


def model_status(weights: dict, *, live_forward_active: bool = False) -> str:
    """FROZEN/VALIDATED/EXPERIMENTAL -- función pura (sin red, sin base de
    datos): `live_forward_active` lo decide el llamador (ver
    current_model_status para la versión que sí consulta las fuentes reales).

    - EXPERIMENTAL: `weights` se desvía de la hipótesis congelada, sea cual
      sea la magnitud.
    - LIVE_FORWARD: coincide con la hipótesis congelada Y hay seguimiento
      en vivo activo (una validación ciega bloqueada con rebalanceos reales,
      o al menos un experimento en fase LIVE_FORWARD).
    - VALIDATED: coincide con la hipótesis congelada pero sin seguimiento
      en vivo activado todavía."""
    if not weights_match_frozen(weights):
        return "EXPERIMENTAL"
    return "LIVE_FORWARD" if live_forward_active else "VALIDATED"


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


def visible_pages(mode: str, all_page_paths: list) -> list:
    """Filtra `all_page_paths` (rutas tal y como las pasa streamlit_app.py
    a st.Page) según el modo -- RESEARCH ve todas; INVESTOR, solo
    INVESTOR_PAGES. Preserva el orden de entrada."""
    if mode not in MODES:
        raise ValueError(f"mode debe ser uno de {MODES}")
    if mode == "RESEARCH":
        return list(all_page_paths)
    return [p for p in all_page_paths if p in INVESTOR_PAGES]


def experimental_banner_message(weights: dict) -> str | None:
    """Mensaje a mostrar cuando `weights` se desvía de la hipótesis
    congelada -- None si coincide (nada que avisar). El guardrail contra
    data snooping accidental: cambiar un peso siempre se ve, nunca es
    silencioso, y apunta a dónde registrar el experimento con trazabilidad."""
    if weights_match_frozen(weights):
        return None
    parts = ", ".join(f"{k.capitalize()} {v:.0%}" for k, v in weights.items())
    return (
        f"🧪 **EXPERIMENTAL** -- estos pesos ({parts}) no son los de la {FROZEN_LABEL}. "
        "Este resultado no es una validación oficial del modelo. Si quieres conservar la "
        "trazabilidad de lo que pruebes, regístralo en 🔬 Research Lab."
    )
