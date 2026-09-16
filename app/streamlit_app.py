"""GABI — punto de entrada de la app Streamlit.

Ejecutar con: streamlit run app/streamlit_app.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import streamlit as st

st.set_page_config(page_title="GABI — Screener", page_icon="📈", layout="wide")

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

GABI puntúa cada empresa del S&P 500 combinando tres bloques de métricas,
cada uno normalizado por percentil **dentro de su sector**:

- **Value** — ¿está barata respecto a sus fundamentales? (PER, PEG, P/B, P/S, EV/EBITDA)
- **Quality** — ¿son sólidos sus fundamentales? (rentabilidad, ROIC, márgenes, deuda,
  crecimiento de ingresos/FCF a 3 años vía SEC EDGAR)
- **Momentum** — ¿hay señales técnicas de entrada en fase alcista? (medias móviles, RSI, fuerza relativa vs SPY)

El **Composite Score** es la media ponderada de los tres bloques, con pesos
que puedes ajustar tú mismo. El objetivo no es solo darte un ranking, sino
que puedas ver **por qué** una empresa puntúa bien, empresa a empresa.

### Primeros pasos

1. Ve a **⚙️ Configuración** y pulsa "Actualizar datos" (empieza con un
   subconjunto pequeño para probar rápido).
2. Ve a **📊 Screener** para buscar empresas, ver el ranking y ajustar filtros/pesos.
3. Haz clic en una empresa para ver su **🔍 Ficha**: desglose completo del score
   y enlaces directos a su último 10-K/10-Q oficial (SEC EDGAR).
4. Consulta el **🌐 Panel Macro** (tipos, inflación, curva, crédito) para tener
   contexto — requiere una API key gratuita de FRED (se configura en ⚙️).
5. Antes de invertir, escribe tu tesis en el **📓 Diario de inversión**: precio de
   entrada, escenarios de valoración, catalizadores y qué demostraría que te
   equivocaste. Revísala pasados unos meses — se aprende más así que acumulando
   indicadores.
    """
)
