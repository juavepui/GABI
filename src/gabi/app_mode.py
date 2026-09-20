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
    current_model_status para la versión que sí consulta el Research Lab).

    - EXPERIMENTAL: `weights` se desvía de la hipótesis congelada, sea cual
      sea la magnitud.
    - LIVE_FORWARD: coincide con la hipótesis congelada Y hay seguimiento
      en vivo activo (al menos un experimento en fase LIVE_FORWARD).
    - VALIDATED: coincide con la hipótesis congelada pero sin seguimiento
      en vivo activado todavía."""
    if not weights_match_frozen(weights):
        return "EXPERIMENTAL"
    return "LIVE_FORWARD" if live_forward_active else "VALIDATED"


def current_model_status() -> dict:
    """Envoltorio NO puro sobre model_status()/weights_match_frozen(): lee
    los pesos guardados (config.load_weights) y si hay algún experimento
    LIVE_FORWARD registrado (research_lab) -- para que la UI solo tenga que
    llamar a esto una vez, sin repetir la lógica de qué cuenta como
    FROZEN/EXPERIMENTAL en cada página."""
    from . import research_lab  # import diferido: no acopla este módulo a research_lab/storage en import time
    weights = config.load_weights()
    try:
        live_forward_active = not research_lab.list_experiments(stage="LIVE_FORWARD").empty
    except Exception:
        live_forward_active = False  # el estado del modelo no debe romperse porque falle una consulta secundaria
    matches = weights_match_frozen(weights)
    return {
        "status": model_status(weights, live_forward_active=live_forward_active),
        "weights": weights,
        "model_id": FROZEN_MODEL_ID if matches else "EXPERIMENTAL",
        "matches_frozen": matches,
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
