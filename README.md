# GABI — Screener de acciones (fundamentales + momentum)

Herramienta de uso **personal y educativo** para analizar empresas del S&P 500
combinando métricas fundamentales (valor y calidad) con señales técnicas de
momentum, con el objetivo de identificar candidatas a entrar en una fase
alcista en un horizonte de 6-12 meses, y sobre todo **entender por qué**.

> ⚠️ **No es asesoramiento financiero.** Los datos vienen de fuentes gratuitas
> (Yahoo Finance vía `yfinance`) y pueden tener errores, retraso o estar
> incompletos. Verifica siempre por tu cuenta antes de invertir.

## Instalación

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

## Uso

```bash
streamlit run app/streamlit_app.py
```

1. En **⚙️ Configuración**, pulsa "Actualizar datos" (empieza con el
   subconjunto de 50 empresas para probar rápido; la primera descarga de
   fundamentales de las 500 empresas puede tardar varios minutos porque
   yfinance no permite pedirlos en batch).
2. En **📊 Screener**, ajusta pesos (Value / Quality / Momentum) y filtros
   (sector, capitalización, golden cross) y revisa el ranking.
3. En **🔍 Ficha de empresa**, mira el gráfico de precio con medias móviles y
   el desglose métrica a métrica de por qué una empresa puntúa como puntúa.

Los datos se cachean en `data/gabi.db` (SQLite). Los fundamentales se
consideran frescos 24h; no hace falta actualizar en cada sesión.

## Metodología

Cada métrica se normaliza por **percentil dentro del universo analizado**
(0-100) para poder combinar magnitudes muy distintas:

- **Value** (¿está barata?): PER, PEG, P/B, P/S, EV/EBITDA — invertido (más barato = más puntos).
- **Quality** (¿son buenos los fundamentales?): ROE, ROA, márgenes, deuda/equity (invertida), current ratio, crecimiento de ingresos y beneficios.
- **Momentum** (¿hay señal de entrada alcista?): precio vs SMA50/SMA200, golden cross reciente, RSI14 (zona sana 45-65), momentum a 6/12 meses, fuerza relativa vs SPY.

El **Composite Score** es la media ponderada de los tres bloques (pesos
ajustables en la UI, por defecto 35/35/30).

## Estructura

```
src/gabi/       lógica pura (fetch, storage, métricas, scoring) — testeada con pytest
app/            frontend Streamlit (multipágina)
tests/          pytest, sin red, con datos sintéticos
data/           caché SQLite + CSV de universo (gitignored)
```

## Ejecutar los tests

```bash
pytest tests/
```

## Limitaciones conocidas

- yfinance es una API no oficial y gratuita: puede fallar, tener rate limits
  no documentados o cambiar de esquema entre versiones. El fetch de
  fundamentales tolera fallos individuales sin romper el resto del universo.
- El crecimiento de ingresos "interanual TTM" calculado desde los estados
  financieros trimestrales depende de que yfinance exponga al menos 8
  trimestres, algo que no siempre ocurre en el nivel gratuito — en ese caso
  simplemente se omite esa métrica para esa empresa (no rompe el score).
- No hay ROIC real (requiere datos de balance más completos); se usa ROE +
  ROA como proxy de calidad/rentabilidad.
- Solo cubre S&P 500 / EE.UU. por ahora.

## Próximos pasos (no incluidos en este MVP)

- Capa de IA: dado el desglose de métricas de una empresa preseleccionada,
  pedir a un LLM (API de Claude) un análisis cualitativo en lenguaje natural
  que ayude a interpretar el score. Punto de extensión pensado en
  `src/gabi/scoring.py::explain_row`, que ya deja la tabla de métricas +
  percentiles lista para pasarle a un prompt.
- Actualización programada (cron) en vez de botón manual.
- Backtesting simple del score contra rendimiento real a 6-12 meses.
