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

0. Si vienes sin experiencia previa, empieza por **🎓 Aprender** (términos, estrategias, psicología).
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
4. En **⚖️ Comparar empresas**, elige entre 2 y 5 empresas para verlas lado a
   lado (tabla + gráfico de barras por bloque).
5. En **🕰️ Ranking histórico** (experimental), reconstruye lo que el
   screener habría mostrado en una fecha pasada — sin mirar al futuro.
6. En **🌐 Panel Macro**, consulta el contexto macroeconómico (requiere API
   key de FRED, ver arriba).
7. En **📓 Diario de inversión**, escribe tu tesis antes de invertir y
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
- **Quality** (¿son buenos los fundamentales?): ROE, ROA, ROIC (SEC EDGAR), márgenes, current ratio,
  crecimiento de ingresos y beneficios (YoY y CAGR 3 años vía SEC EDGAR), crecimiento del flujo de
  caja libre a 3 años.
- **Momentum** (¿hay señal de entrada alcista?): precio vs SMA50/SMA200, golden cross reciente, RSI14
  (zona sana 45-65), momentum a 6/12 meses, fuerza relativa vs SPY.
- **Risk** (¿cuánto riesgo hay que asumir?): deuda/equity, volatilidad anualizada, máximo drawdown,
  Sharpe Ratio, Sortino Ratio — todo calculado a partir del histórico de precios ya cacheado, sin
  fuente de datos nueva. Es el equivalente a nivel de una sola empresa de las métricas típicas de
  análisis de carteras (Sharpe, Sortino, beta...); también se muestran de forma informativa (sin
  puntuar) beta, alpha, win rate mensual, rentabilidad por dividendo y volumen medio.

El **Composite Score** es la media ponderada de los cuatro bloques (pesos
ajustables en la UI, por defecto Value 30 / Quality 35 / Momentum 25 / Risk 10).

## Comparar empresas

⚖️ Comparar empresas deja elegir entre 2 y 5 empresas del universo analizado
y verlas lado a lado: un gráfico de barras agrupadas con los 4 scores + el
Composite, y una tabla transpuesta (una fila por métrica, una columna por
empresa) con el mismo color-coding que el Screener — el percentil de color
sigue comparando con todo el sector, no solo con las empresas seleccionadas
aquí, para que el color siga significando lo mismo en toda la app.

## 🎓 Aprender

Pensada para quien empieza desde cero: tres pestañas con **términos útiles**
(glosario, incluyendo un repaso de las métricas que usa GABI reutilizando el
mismo texto que sus tooltips — una sola fuente de verdad), **estrategias de
inversión** (value, growth, dividendos, momentum, indexación pasiva...,
relacionadas con los bloques Value/Quality/Momentum de GABI) y **psicología
de la inversión** (FOMO, sesgo de confirmación, aversión a la pérdida...).
Conecta explícitamente con el 📓 Diario de inversión como la herramienta
práctica contra varios de esos sesgos.

## Navegación

El menú lateral usa `st.navigation`/`st.Page` (API moderna de Streamlit) en
vez del descubrimiento automático por nombre de archivo, para poder darle a
cada página un icono explícito, separado del texto. Todo se define en un solo
sitio: `app/streamlit_app.py`. `st.set_page_config()` y la inyección de CSS
(`gabi.ui_helpers.inject_custom_css()`, que también centra el indicador de
"ejecutando" de Streamlit en la pantalla) se llaman ahí una única vez — las
páginas individuales en `app/pages/` ya no lo hacen (llamarlo dos veces en la
misma ejecución rompe `set_page_config()`).

## Estructura

```
src/gabi/       lógica pura (fetch, edgar, macro, storage, métricas, scoring) — testeada con pytest
app/            frontend Streamlit (multipágina, navegación centralizada en streamlit_app.py)
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
- Sharpe/Sortino/Alpha usan como tipo libre de riesgo el Treasury 10 años en
  vivo (vía FRED, si hay API key configurada) o, si no, una constante fija
  del 4% (`config.RISK_FREE_RATE`) — una simplificación razonable pero no un
  tipo libre de riesgo "correcto" para cada horizonte temporal.
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
  una falsa sensación de que "el modelo funciona".

## Point-in-time: fase 1 y 2 completas, con UI (experimental)

**Fase 1 (ingesta):** `edgar.py` guarda en `edgar_facts` **todo** el
histórico fechado de SEC EDGAR sin filtrar (ingresos, beneficio neto, FCF,
patrimonio, deuda, margen bruto/operativo, D&A, caja, nº de acciones) — cada
hecho con su fecha real de presentación (`filed_date`), incluidas revisiones
posteriores del mismo periodo. `get_value_as_of(symbol, tags, fecha)`
reconstruye qué se sabía en una fecha concreta sin mirar al futuro
(look-ahead bias) — verificado con datos reales de la SEC, incluido un caso
con una restatación posterior real.

**Fase 2 (screener por fecha arbitraria):** `screener_asof.build_ranking_as_of(fecha)`
reconstruye el ranking completo tal y como se habría visto ese día:

- **Universo histórico** (`universe.get_sp500_constituents_asof`): usa
  [`hanshof/sp500_constituents`](https://github.com/hanshof/sp500_constituents)
  (comunidad, MIT, composición diaria desde 1996 hasta 2025-08-23) para
  incluir empresas ya deslistadas/excluidas del índice y evitar el sesgo de
  supervivencia — verificado con datos reales de junio de 2019, que
  correctamente incluye tickers como ABMD, ANTM o ATVI que ya no están en el
  S&P 500 actual. Para fechas posteriores a la cobertura de esa fuente, cae
  de vuelta al universo actual (marcado con `is_exact=False`, con el riesgo
  de sesgo de supervivencia que eso reintroduce).
- **Fundamentales y múltiplos clásicos** (ROIC, margen bruto/operativo/neto,
  deuda neta/EBITDA, crecimiento de ingresos/FCF, PER, P/VC, P/Ventas,
  EV/EBITDA): 100% desde `edgar_facts` + precio y nº de acciones de esa
  fecha — nunca yfinance, que no guarda histórico.
- **Momentum y riesgo**: reutiliza `technicals.py`/`risk.py` sin cambios,
  simplemente truncando el histórico de precios a `fecha`.

Verificado con datos reales de Apple y Microsoft a junio de 2019: ROIC,
márgenes, deuda/patrimonio y crecimiento salen correctos y coherentes con
cifras públicas conocidas de esos ejercicios. También hay página en la app —
**🕰️ Ranking histórico** — con selector de fecha, un botón para descargar lo
que falte para esa fecha concreta (SEC EDGAR + histórico de precios
profundo) y la misma tabla con semáforo de colores que el resto de la app.
Marcada como experimental a propósito.

**Split de acciones — bug real encontrado y corregido al verificar con
datos reales:** yfinance devuelve el precio siempre ajustado por splits
futuros (con o sin `auto_adjust`), pero el nº de acciones de SEC EDGAR es
el real de esa fecha, sin ajustar. Multiplicarlos directamente daba una
capitalización sistemáticamente mal por el factor del split — comprobado
con Apple (split 4:1 en 2020): la capitalización de junio de 2019 salía
~$190 mil M en vez de los ~$850 mil M reales. Se corrige guardando el
historial de splits (`storage.splits`, `data_fetch.fetch_splits_batch`) y
deshaciendo los splits posteriores a la fecha consultada antes de calcular
la capitalización — verificado que ahora sale ~$849 mil M y un PER ~14.3,
coherentes con cifras públicas de esa fecha.

**Limitaciones conocidas de esta reconstrucción:**
- El histórico de **precios** normal solo cubre ~2 años hacia atrás. Para
  fechas más antiguas, 🕰️ Ranking histórico ofrece un botón para pedir el
  histórico completo (`period="max"`) — pero solo para los símbolos que aún
  no lleguen tan atrás, no para todo el universo en cada refresco normal
  (sería mucho más lento/pesado para un caso de uso ocasional).
- El sector/nombre de una empresa se toma del universo **actual**: las
  empresas ya deslistadas quedan sin sector (el scoring cae automáticamente
  al percentil sobre todo el universo para esas filas en vez de romper).
- **Los tickers se reciclan** — riesgo real, no solo teórico: comprobado que
  "APC" (Anadarko Petroleum en 2019) hoy en el mapeo de la SEC apunta a
  "ARKO Petroleum Corp", una empresa completamente distinta; "BBT" (BB&T) hoy
  es "Beacon Financial Corp". El mapeo ticker→CIK de SEC EDGAR es el
  **actual**, así que resolverlo a ciegas para una fecha pasada puede
  atribuir los datos de una empresa equivocada. Mitigación: se guarda una
  caché local persistente de resoluciones (`edgar.cik_resolutions`, símbolo
  ya resuelto una vez sigue siéndolo aunque desaparezca del mapeo en vivo) y
  cada fila de 🕰️ Ranking histórico muestra el **nombre registrado en la
  SEC**, no solo el ticker — para que un reciclaje se note a simple vista.
  No hay forma gratuita de verificarlo automáticamente.

Si en algún momento se paga acceso a un proveedor point-in-time (tipo
Sharadar), sustituiría/complementaría esto — pero de momento todo lo
anterior es gratis.

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
