# GABI — Screener de acciones (fundamentales + momentum)

Herramienta de uso **personal y educativo** para analizar empresas del S&P 500
combinando métricas fundamentales (valor y calidad) con señales técnicas de
momentum, con el objetivo de identificar candidatas a entrar en una fase
alcista en un horizonte de 6-12 meses, y sobre todo **entender por qué**.

> ⚠️ **No es asesoramiento financiero.** Los datos vienen de fuentes gratuitas
> (Yahoo Finance, SEC EDGAR, FRED) y pueden tener errores, retraso o estar
> incompletos. Verifica siempre por tu cuenta antes de invertir.

## Fuentes de datos

- **Yahoo Finance** (`yfinance`) — precios y fundamentales básicos. Gratis, sin API key.
- **SEC EDGAR** (XBRL) — ROIC aproximado, crecimiento de ingresos/FCF a 3 años (CAGR)
  y enlaces directos al último 10-K/10-Q de cada empresa, directamente de los
  informes oficiales. Gratis, sin API key.
- **FRED** (Federal Reserve Economic Data) — panel macro (tipos, inflación,
  curva de tipos, crédito, dólar, liquidez, ciclo). Gratis, pero requiere una
  API key propia (alta inmediata, sin tarjeta, en
  [fred.stlouisfed.org/docs/api/api_key.html](https://fred.stlouisfed.org/docs/api/api_key.html))
  — pégala en ⚙️ Configuración.

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
   fundamentales + SEC EDGAR de las 500 empresas puede tardar varios minutos
   porque ninguna de las dos APIs permite pedir todo en batch, y la SEC es
   especialmente estricta con el ritmo de peticiones).
2. En **📊 Screener**, busca empresas, ajusta pesos (Value / Quality /
   Momentum) y filtros (sector, capitalización, golden cross) y revisa el ranking.
3. En **🔍 Ficha de empresa**, mira el gráfico de precio, el desglose métrica
   a métrica de por qué una empresa puntúa como puntúa, y abre su último
   10-K/10-Q directamente desde SEC EDGAR.
4. En **🌐 Panel Macro**, consulta el contexto macroeconómico (requiere API
   key de FRED, ver arriba).
5. En **📓 Diario de inversión**, escribe tu tesis antes de invertir y
   revísala pasados unos meses.

Los datos se cachean en `data/gabi.db` (SQLite). Los fundamentales de Yahoo se
consideran frescos 24h; los de SEC EDGAR, 7 días (cambian con cada 10-K/10-Q,
no a diario); no hace falta actualizar en cada sesión.

## Metodología

Cada métrica se normaliza por **percentil dentro de su sector GICS** (0-100) —
comparar el EV/EBITDA de un banco con el de una tecnológica no tiene sentido.
Si un sector tiene muy pocas empresas con dato en el universo analizado (por
defecto, menos de 8), esa métrica cae de vuelta al percentil sobre todo el
universo para evitar puntuaciones artificialmente perfectas por tamaño de
muestra pequeña. Esto permite combinar magnitudes muy distintas:

- **Value** (¿está barata?): PER, PEG, P/B, P/S, EV/EBITDA — invertido (más barato = más puntos).
- **Quality** (¿son buenos los fundamentales?): ROE, ROA, ROIC (SEC EDGAR), márgenes, deuda/equity
  (invertida), current ratio, crecimiento de ingresos y beneficios (YoY y CAGR 3 años vía SEC EDGAR),
  crecimiento del flujo de caja libre a 3 años.
- **Momentum** (¿hay señal de entrada alcista?): precio vs SMA50/SMA200, golden cross reciente, RSI14
  (zona sana 45-65), momentum a 6/12 meses, fuerza relativa vs SPY.

El **Composite Score** es la media ponderada de los tres bloques (pesos
ajustables en la UI, por defecto 35/35/30).

## Estructura

```
src/gabi/       lógica pura (fetch, edgar, macro, storage, métricas, scoring) — testeada con pytest
app/            frontend Streamlit (multipágina)
tests/          pytest, sin red, con datos sintéticos/mockeados
data/           caché SQLite + CSVs + claves locales (todo gitignored)
```

## Ejecutar los tests

```bash
pytest tests/
```

## Limitaciones conocidas

- Ninguna de las tres fuentes es oficial-comercial ni tiene SLA: pueden
  fallar, tener rate limits no documentados o cambiar de esquema. El fetch
  tolera fallos individuales sin romper el resto del universo, y ⚙️
  Configuración explica el motivo de cada fallo agrupado (rate limit, ticker
  sin datos, timeout...).
- El crecimiento de ingresos "interanual TTM" calculado desde los estados
  financieros trimestrales de yfinance depende de que exponga al menos 8
  trimestres, algo que no siempre ocurre en el nivel gratuito. Para esto, el
  CAGR a 3 años de SEC EDGAR (histórico anual real desde los 10-K) es más
  fiable — pero puede faltar en empresas con menos de 4 años de 10-K
  presentados electrónicamente (IPOs recientes) o si aún no se ha
  descargado desde ⚙️ Configuración.
- El ROIC es una aproximación (NetIncomeLoss / (patrimonio neto + deuda a
  largo plazo), sin ajuste fiscal) y puede faltar si la empresa no usa las
  etiquetas XBRL habituales (frecuente en empresas casi sin deuda a largo plazo).
- El panel macro no se usa (todavía) dentro del score: mezclar factores con
  régimen macro sin verificar históricamente qué funciona y cuándo sería
  fingir una precisión que no existe. Ver "Backtesting" más abajo.
- Solo cubre S&P 500 / EE.UU. por ahora.

## Por qué NO hay (todavía) backtesting ni Alpha Vantage

Se evaluó explícitamente añadir Alpha Vantage (earnings surprises, insider
buying, noticias) y un motor de backtesting histórico multi-factor, y se
decidió no hacerlo por ahora:

- **Alpha Vantage**: su nivel gratuito es demasiado limitado para cientos de
  empresas: requeriría un plan de pago.
- **Backtesting**: para que un backtest no mienta hace falta usar
  fundamentales *tal y como se conocían en cada fecha histórica*, no los
  actuales — de lo contrario se introduce look-ahead bias y el resultado da
  una falsa sensación de que "el modelo funciona". Los datos gratuitos de
  yfinance/SEC EDGAR no dan eso de forma fiable (solo exponen el estado
  actual); haría falta un proveedor de pago con datos point-in-time (tipo
  Sharadar). Si en algún momento se paga ese acceso, es el siguiente paso
  natural antes de plantearse Machine Learning sobre el ranking.

## Capa de IA: generador de prompt (no llamada a API)

En 🔍 Ficha de empresa hay una sección "🤖 Prompt para analizar con IA"
(`src/gabi/ai_prompt.py`) que construye un prompt listo para pegar en el
asistente que prefieras (Claude, ChatGPT...). Regla de diseño explícita:
**la IA nunca calcula métricas financieras** — los números del prompt salen
siempre de `scoring.py`/`metrics.py`/`edgar.py` (código determinista sobre
datos ya descargados); a la IA se le pide interpretar esos números y los
documentos fuente que el usuario pegue (10-K/10-Q enlazados automáticamente,
earnings call, guidance, noticias), no inventar cifras nuevas. No se llama a
ninguna API de IA desde GABI — evita una decisión de presupuesto/API key
adicional y deja a criterio del usuario qué asistente usar.

## Próximos pasos (no incluidos en este MVP)

- Automatizar la llamada al LLM (API de Claude) en vez de copiar/pegar el
  prompt manualmente, si en algún momento se decide asumir el coste de API.
- Actualización programada (cron) en vez de botón manual.
- Backtesting con datos point-in-time (ver arriba) y, solo después, modelos
  de Machine Learning interpretables (regresión, Random Forest, XGBoost) con
  walk-forward validation — nunca mezclando aleatoriamente pasado y futuro.
