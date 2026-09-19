"""GABI — punto de entrada de la app Streamlit.

Usa st.navigation/st.Page (API moderna de Streamlit) en vez del descubrimiento
automático por nombre de archivo, para poder darle a cada página un icono
explícito en el menú lateral, separado del texto — st.set_page_config() y
gabi.ui_helpers.inject_custom_css() se llaman aquí, una sola vez, y ya no en
cada página individual (llamarlo dos veces en la misma ejecución rompe
set_page_config()).

Ejecutar con: streamlit run app/streamlit_app.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import streamlit as st

from gabi.ui_helpers import inject_custom_css

st.set_page_config(page_title="GABI — Screener", page_icon="📈", layout="wide")
inject_custom_css()


def inicio():
    st.title("📈 GABI — Screener de acciones (S&P 500)")

    st.warning(
        "⚠️ Herramienta de uso personal y educativo. **No es asesoramiento financiero.** "
        "Los datos vienen de fuentes gratuitas (Yahoo Finance, SEC EDGAR, FRED) y pueden "
        "tener retraso o errores. Verifica siempre antes de invertir.",
        icon="⚠️",
    )

    st.markdown(
        """
### Cómo funciona

GABI puntúa cada empresa del S&P 500 combinando cuatro bloques de métricas,
cada uno normalizado por percentil **dentro de su sector**:

- **Value** — PER, P/B y EV/EBITDA.
- **Quality** — ROIC, margen operativo y crecimiento de ingresos/FCF a 3 años.
- **Momentum** — 12 meses, fuerza relativa a 6 meses y precio frente a SMA200.
- **Risk** — deuda, volatilidad y máximo drawdown.

El **Composite Score** es la media ponderada de los cuatro bloques, con pesos
que puedes ajustar tú mismo. El objetivo no es solo darte un ranking, sino
que puedas ver **por qué** una empresa puntúa bien, empresa a empresa.

### Primeros pasos

1. Si estás empezando, echa un vistazo a **🎓 Aprender**: términos, estrategias, psicología de la
   inversión, y cómo piensa GABI por dentro (con sus sesgos, límites y motores V1/V2).
2. Ve a **⚙️ Configuración** y pulsa "Actualizar datos" (empieza con un
   subconjunto pequeño para probar rápido).
3. Ve a **📊 Screener** para buscar empresas, ver el ranking y ajustar filtros/pesos.
4. Haz clic en una empresa para ver su **🔍 Ficha**: desglose completo del score
   y enlaces directos a su último 10-K/10-Q oficial (SEC EDGAR).
5. Usa **⚖️ Comparar empresas** para ver 2-5 empresas lado a lado, tabla y gráfico.
6. Consulta el **🌐 Panel Macro** (tipos, inflación, curva, crédito) para tener
   contexto — requiere una API key gratuita de FRED (se configura en ⚙️).
7. Antes de invertir, escribe tu tesis en el **📓 Diario de inversión**: precio de
   entrada, escenarios de valoración, catalizadores y qué demostraría que te
   equivocaste. Revísala pasados unos meses — se aprende más así que acumulando
   indicadores.
8. En **🧭 Decisiones de cartera**, introduce tus posiciones y genera un plan
   de compra, mantenimiento o venta con pesos objetivo y límites de riesgo.
9. En **🧪 Carteras simuladas**, crea varias carteras, registra operaciones
   históricas con costes supuestos y compara sus resultados con SPY.
        """
    )


pages = [
    st.Page(inicio, title="Inicio", icon="📈", default=True),
    st.Page("pages/7_Aprender.py", title="Aprender", icon="🎓"),
    st.Page("pages/1_Screener.py", title="Screener", icon="📊"),
    st.Page("pages/2_Ficha_Empresa.py", title="Ficha de empresa", icon="🔍"),
    st.Page("pages/6_Comparar_Empresas.py", title="Comparar empresas", icon="⚖️"),
    st.Page("pages/8_Ranking_Historico.py", title="Ranking histórico", icon="🕰️"),
    st.Page("pages/11_Research_Lab.py", title="Research Lab", icon="🔬"),
    st.Page("pages/12_Factor_Lab.py", title="Factor Lab", icon="📐"),
    st.Page("pages/13_Blind_Validation.py", title="Blind Forward Validation", icon="🔒"),
    st.Page("pages/14_Portfolio_Lab.py", title="Portfolio Lab", icon="🧮"),
    st.Page("pages/9_Decisiones.py", title="Decisiones de cartera", icon="🧭"),
    st.Page("pages/10_Carteras_Simuladas.py", title="Carteras simuladas", icon="🧪"),
    st.Page("pages/5_Panel_Macro.py", title="Panel Macro", icon="🌐"),
    st.Page("pages/4_Diario_Inversion.py", title="Diario de inversión", icon="📓"),
    st.Page("pages/15_Salud_Datos.py", title="Salud de los datos", icon="🩺"),
    st.Page("pages/3_Configuracion.py", title="Configuración", icon="⚙️"),
]

st.navigation(pages).run()
