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
8. En **🧭 Decisiones de cartera**, introduce tus posiciones actuales como
   `TICKER,porcentaje` y genera un plan de compra, mantenimiento o venta.
9. En **🧪 Carteras simuladas**, crea varias carteras, añade compras/ventas
   fechadas, compara cada resultado con SPY y prueba una estrategia de medias.

Las operaciones simuladas usan `exchange_calendars` para seleccionar la primera
sesión del mercado elegido desde la fecha indicada. Si falta esa cotización en el caché, la
operación se detiene en vez de ejecutarse a un precio de otra sesión. Los
resultados se calculan con cierres públicos y costes supuestos, sin conexión
operativa con el bróker.

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
  Sharpe Ratio, Sortino Ratio — calculados a partir del histórico de precios ya cacheado, sin
  fuente de datos nueva. Es el equivalente a nivel de una sola empresa de las métricas típicas de
  análisis de carteras (Sharpe, Sortino, beta...); beta, alpha, win rate mensual,
  rentabilidad por dividendo y volumen medio también se muestran como contexto.

El **Composite Score** es la media ponderada de los cuatro bloques (pesos
ajustables en la UI, por defecto Value 30 / Quality 35 / Momentum 25 / Risk 10).
Para evitar contar varias veces señales muy correlacionadas, el score utiliza
solo 13 métricas representativas: Value (PER, P/B, EV/EBITDA), Quality (ROIC,
margen operativo, CAGR de ingresos y FCF), Momentum (12 meses, fuerza relativa
a 6 meses, precio frente a SMA200) y Risk (deuda/equity, volatilidad y máximo
drawdown). Las demás métricas se muestran como contexto, sin puntuar. Se muestra
la cobertura de cada empresa; con menos del 50 % o sin algún dato en Value,
Quality o Momentum, no se publica un Composite Score.

El screener permite guardar el top de cada día. Cuando transcurren 6 o 12 meses,
compara su rentabilidad total equiponderada con SPY y muestra la cobertura de
precios. El ranking histórico permite explorar esa comparación para una fecha
pasada y contrastar los cuatro bloques por separado. Una sola fecha no valida
los pesos; harían falta varias fechas y una muestra posterior fuera del ajuste.

## Decisiones de cartera y proyectos integrados

GABI usa [PyPortfolioOpt](https://github.com/PyPortfolio/PyPortfolioOpt) para
asignar pesos mediante mínima volatilidad y covarianza Ledoit-Wolf sobre hasta
252 sesiones comunes de precios ajustados por dividendos. Aplica después topes
por empresa, sector y capital invertido; el resto queda en efectivo. Si falla el
optimizador, utiliza pesos inversos a volatilidad y lo indica en el plan.
Usa [QuantStats](https://github.com/ranaroussi/quantstats) para mostrar Sharpe y
drawdown de la combinación propuesta sobre el histórico disponible. Son medidas
retrospectivas, no una predicción.

El motor solo considera empresas con score y cobertura suficientes, precio
reciente por encima de SMA200, volatilidad <=60 %, drawdown >=-50 % y al menos
126 sesiones de rentabilidad. Por defecto permite 10 empresas, 5 % por empresa,
20 % por sector y 50 % de la cartera en esas acciones. Compara los pesos objetivo
con las posiciones que introduzcas y devuelve COMPRAR, MANTENER, REDUCIR o VENDER.
Una posición sin datos recientes queda en REVISAR. Cada plan se guarda en SQLite
y se puede descargar en CSV, cambiar de nombre o borrar desde **Planes anteriores**.
Al generar decisiones, la app completa los cierres ajustados que falten en la
caché antigua y actualiza precios obsoletos; muestra los símbolos cuya descarga
falle. La primera preparación puede tardar varios minutos si afecta a todo el
S&P 500. No hay conexión a un bróker ni envío de órdenes.

También se evaluaron [Qlib](https://github.com/microsoft/qlib),
[FinRL](https://github.com/AI4Finance-Foundation/FinRL) y
[VectorBT](https://github.com/polakowo/vectorbt). Son útiles para investigación
y backtesting, pero no se incorporan al motor de decisión actual: entrenar o
optimizar sobre el histórico incompleto de GABI podría dar decisiones engañosas.

Las reglas de este motor aún no tienen una validación prospectiva suficiente.
Los planes son decisiones mecánicas de una política explícita; no hay evidencia
de que superen a un índice.

## Carteras simuladas y backtesting

La pestaña **Carteras simuladas** guarda en SQLite carteras independientes con
capital inicial en USD o EUR. Cada operación utiliza el primer cierre del
mercado elegido desde la fecha solicitada; si falta ese cierre en el caché,
no se registra. La valoración posterior usa precios ajustados por dividendos.
El motor comprueba
que haya efectivo para comprar y posición suficiente para vender, mantiene un
registro de comisiones y spread aplicado por operación, y permite deshacer la
última operación introducida. Compara la curva de valor y el retorno de cada
cartera con una compra inicial de SPY en el mismo periodo. Se pueden indicar
comisión, spread, divisa de cotización, cambio y coste de conversión en cada
operación. Para valorar una cartera en otra divisa se necesita el histórico
de cambio de Yahoo Finance; el tipo introducido manualmente solo se aplica a
la operación correspondiente. Las carteras antiguas se migran a USD sin
alterar sus transacciones.

La sección **Probar estrategia** integra
[Backtesting.py](https://github.com/kernc/backtesting.py) para contrastar un
cruce de medias móviles contra comprar y mantener, con comisión y spread
configurables. La señal se calcula al cierre y la orden simulada se ejecuta en
la sesión siguiente. Este test individual no incluye dividendos; las carteras
manuales sí usan `Adj Close` para medir rentabilidad total.

La [tabla oficial de eToro](https://www.etoro.com/es/trading/fees/) indica que
algunas acciones tienen 1 o 2 USD de comisión por apertura y cierre según
residencia y bolsa, mientras que los ETF no tienen comisión de operación. El
diferencial de mercado varía y eToro no ofrece en esa tabla un histórico por
instrumento. Por eso cada cartera tiene una **hipótesis editable** de comisión
y spread (por defecto 1 USD por acción, 0 por ETF y 10 puntos básicos de spread
total, cifra supuesta, no tarifa oficial). La conversión de divisa se simula
con el cambio y coste indicado; no se modelan impuestos, CFD ni financiación.
eToro expresa ciertas comisiones de acciones en USD aunque el activo cotice
en otra divisa: GABI pide introducir el equivalente en la divisa del ticker.
Todos los datos externos se consultan en modo
lectura y ninguna función se conecta a una cuenta de eToro o envía órdenes.

En **Ranking histórico**, el backtest multifactor reconstruye el ranking en
cada rebalanceo, selecciona las primeras candidatas con cobertura suficiente
y empieza a medir rentabilidad en la sesión posterior a la señal. Exige
composición histórica exacta del S&P 500 y precios ajustados en entrada y
salida para todas las candidatas y SPY. La fuente gratuita de composición
termina en 2025 y puede contener símbolos reutilizados; el test se detiene
fuera de su cobertura. La curva solo muestra resultados entre rebalanceos,
por lo que su drawdown no representa las caídas intraperiodo.

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

## Límites del backtesting histórico y de Alpha Vantage

Se evaluó añadir Alpha Vantage (earnings surprises, insider buying, noticias)
y un motor histórico multifactor. La app ya incluye una prueba técnica de
cruce de medias y un backtest multifactor exploratorio. Todavía no hay un
backtest institucional con identidad empresarial e historial completo verificados:

- **Alpha Vantage**: su nivel gratuito es demasiado limitado para cientos de
  empresas: requeriría un plan de pago. El insider buying que ofrecía ya se
  cubre gratis vía SEC Form 4 (ver más abajo), sin necesidad de pagarlo.
- **Backtesting multifactor**: para que un backtest no mienta hace falta usar
  fundamentales *tal y como se conocían en cada fecha histórica*, no los
  actuales — de lo contrario se introduce look-ahead bias y el resultado da
  una falsa sensación de que "el modelo funciona".

### Primer resultado real (2019, 50 empresas, rebalanceo trimestral)

Ejecutado desde 🕰️ Ranking histórico con los parámetros por defecto del
formulario (umbrales de cobertura relajados a 60% — con solo 13 métricas
puntuables, el 70% por defecto excluía demasiadas empresas con datos
parciales):

| Periodo | Estrategia | SPY |
|---|---|---|
| Ene→Abr 2019 | +22.2% | +17.4% |
| Abr→Jul 2019 | +0.3% | +3.8% |
| Jul→Oct 2019 | −5.3% | −3.3% |
| Oct 2019→Ene 2020 | +6.8% | +12.2% |
| **Año completo** | **+24.1%** | **+32.1%** |

**La estrategia perdió contra el SPY por ~8 puntos en este único año/subconjunto.**
No es una conclusión — es un solo año con 50 de 500 empresas y varias
limitaciones ya documentadas (universo histórico hasta 2025, reciclaje de
tickers, umbrales relajados) — pero es el primer dato real, y de momento no
hay evidencia de que el score bata al índice. Antes de fiarse del score como
señal de compra, hace falta correrlo en más periodos/universos y mirar los
resultados con ojo crítico.

Al intentar obtener este resultado se encontraron y corrigieron dos bugs
reales que habrían bloqueado el backtest para cualquiera que lo ejecutara:

1. Cientos de símbolos tenían fundamentales SEC EDGAR "frescos" en caché
   (`edgar_metrics`) pero **sin el histórico fechado** (`edgar_facts`) que
   hace falta para reconstruir una fecha pasada — se cachearon antes de que
   existiera esa tabla, y el chequeo de "¿hace falta actualizar?" solo
   miraba la fecha de descarga, no si el dato requerido existía de verdad.
   `ensure_edgar_data` ahora también comprueba `get_symbols_with_facts`.
2. Muchas empresas (comprobado con Abbott) no etiquetan el nº de acciones en
   circulación en la taxonomía `us-gaap` que se buscaba — lo hacen en la
   portada del informe, taxonomía `dei` (`EntityCommonStockSharesOutstanding`).
   Sin eso, no hay capitalización de mercado ni PER/P-VC posibles.
   `_extract_raw_facts` ahora busca en ambas taxonomías.

### Segundo resultado, más robusto (2016-2025, hasta 200 empresas, rebalanceo trimestral)

El resultado de un solo año no permitía concluir nada, así que se repitió el
ejercicio con un rango mucho más largo (universo de hasta 200 empresas por
trimestre) y con un tercer punto de comparación además de SPY: el retorno
equal-weight de **todo** el universo elegible de cada trimestre (no solo el
top-10), para separar si el ranking añade algo o si la diferencia viene solo
de invertir equal-weight en vez de por capitalización.

Al preparar este rango se encontró y corrigió otro bug real: los tickers con
notación de clase por punto (`BRK.B`, Berkshire Hathaway) nunca resolvían
CIK en la SEC porque su archivo de mapeo usa guión (`BRK-B`) — es la misma
acción, pero como cadena de texto no coincidía. `get_cik_for_symbol` ahora
normaliza el punto a guión como *fallback* antes de rendirse (no es "adivinar
otra empresa", es la misma seguridad con otra notación). Corregir esto amplió
el universo elegible en cada trimestre (de ~120-145 a ~144-185 empresas) y
**cambió de forma no trivial los números del rango 2016-2024 ya reportados
antes** — una muestra de lo sensible que es este backtest a huecos de datos
aparentemente pequeños; cualquier cifra concreta aquí debe tratarse como
aproximada, no como verdad exacta.

Quedan además **9 empresas activas hoy que no se pueden resolver**: EA, Bank
of NY Mellon (BK), AvalonBay (AVB), Equity Residential (EQR), Coterra (CTRA),
Fiserv (FI), Dayforce (DAY), Ansys (ANSS) y Discover (DFS). Se confirmó
manualmente contra `data.sec.gov/submissions/` que son registrantes SEC
activos — el hueco está en el archivo `company_tickers.json` de la propia
SEC, no en nuestro código; no se ha implementado un *fallback* de búsqueda
por nombre porque el diseño actual evita deliberadamente adivinar (ver
docstring de `get_cik_for_symbol`).

De los trimestres del rango, los anteriores a 2016-07 se descartan por
cobertura SEC EDGAR insuficiente (ver la siguiente sección), y **más allá de
2025-08-23 no hay composición histórica verificada del índice** — el dataset
gratuito de constituyentes del S&P 500 no llega más lejos, así que 2025-10 en
adelante también se descarta (usar el universo *actual* como aproximación
introduciría sesgo de supervivencia). El resultado cubre los **37 trimestres
de 2016-07 a 2025-07**, los tres últimos (2025) siendo la evidencia más
reciente y menos susceptible de haber influido en el diseño del score:

| Estrategia | Acumulado | Anualizado | Vol. anualizada | Sharpe | Sortino | Máx. drawdown |
|---|---|---|---|---|---|---|
| **Top-10 del ranking** | **+351.4%** | +17.70% | 19.98% | **0.69** | **1.10** | −29.3% |
| Universo equal-weight (sin ranking) | +177.1% | +11.65% | 18.81% | 0.41 | 0.61 | −28.6% |
| SPY (cap-weighted) | +235.1% | +13.97% | 17.64% | 0.56 | 0.85 | −23.9% |

Top-10 le gana al universo equal-weight el 59% de los trimestres y al SPY el
62%. **El ranking sigue compensando el riesgo adicional que asume**: más
volatilidad que el SPY (esperable con 10 posiciones en vez de 500), pero
Sharpe y Sortino claramente mejores — no es solo "más riesgo, más retorno".

**Los tres trimestres de 2025 (el dato real más reciente) no son buenos**:

| Periodo | Top-10 | SPY |
|---|---|---|
| 2025-01 | −4.1% | −4.0% |
| 2025-04 | −0.1% | **+9.5%** |
| 2025-07 | +2.6% | +7.8% |

El ranking se quedó muy por detrás del SPY en 2 de los 3 últimos trimestres
reales. Un inversor profesional no debería sobreinterpretar ni lo positivo
del acumulado de 9 años ni lo negativo de estos 3 últimos trimestres — pero
ambos hechos son reales y hay que tenerlos en cuenta a partes iguales.

Otras salvedades que se mantienen:

- **59-62% no es un margen enorme** — es una ventaja real pero modesta que la
  capitalización compuesta amplifica visualmente; con menos periodos podría
  no ser significativa.
- **Un solo régimen de mercado**: 2016-2025 es mayoritariamente alcista con
  una caída rápida (COVID) y una corrección (2022) — no incluye un mercado
  bajista prolongado (ver más abajo por qué no se pudo ampliar hacia atrás).
- El backtest estándar del módulo (`multifactor_backtest.run`, el que usa el
  botón de la interfaz) **aborta el rango entero** si un solo trimestre no
  llega al umbral de cobertura, en vez de saltarlo — por eso este resultado
  se obtuvo con un script aparte que sí salta trimestres individuales; para
  reproducirlo tal cual desde la UI hay que arrancar en 2016-07 y terminar en
  2025-07.
- En la única caída generalizada real de la muestra (COVID, 2020-01-01) la
  concentración en 10 posiciones no protegió nada frente a tener todo el
  universo (−29.3% vs −28.6%) y fue peor que el SPY (−23.9%) — el ranking
  puntúa mejor "quién sube más", no "quién cae menos" en un pánico de mercado
  (ver el experimento de nº de posiciones justo abajo).

### Experimento: más posiciones y un filtro de tendencia, ¿bajan el drawdown?

Con la caída del COVID como punto débil identificado, se probaron dos ideas
simples sobre el mismo rango 2016-2025: ampliar de 10 a 20/30 posiciones, y
reducir a la mitad la exposición cuando el SPY entra en el rebalanceo por
debajo de su SMA200 (señal de tendencia bajista, la misma que ya se usa a
nivel de empresa individual en 🔍 Ficha de empresa).

| Variante | Acumulado | Anualizado | Sharpe | Sortino | Máx. drawdown |
|---|---|---|---|---|---|
| Top-10 (base) | +351.4% | +17.70% | **0.69** | **1.10** | −29.3% |
| **Top-20** | +288.1% | +15.79% | 0.68 | 1.08 | **−25.6%** |
| Top-30 | +251.0% | +14.54% | 0.61 | 0.92 | −27.1% |
| Top-10 + filtro SMA200 del SPY (50% en bajista) | +231.3% | +13.83% | 0.55 | 0.79 | −29.3% |
| SPY | +235.1% | +13.97% | 0.56 | 0.85 | −23.9% |

**Pasar de 10 a 20 posiciones funciona**: el máximo drawdown baja de −29.3%
a −25.6% (una reducción real) sacrificando prácticamente nada de Sharpe
(0.69→0.68) ni de Sortino (1.10→1.08). Subir a 30 posiciones ya no compensa
— diluye demasiado la ventaja del *stock-picking* (Sharpe 0.61) sin bajar más
el drawdown (−27.1%, peor que con 20). **Recomendación: 20 posiciones en vez
de 10 es una mejora casi gratis.**

**El filtro de SMA200 del SPY no funcionó, y es importante entender por
qué**: en el trimestre de la caída del COVID (2020-01-01) el SPY *todavía
estaba por encima* de su SMA200 al empezar el trimestre — el desplome fue
tan rápido (febrero-marzo 2020) que una media móvil de 200 sesiones, que por
diseño reacciona con retraso, no llegó a activarse a tiempo. El drawdown
máximo quedó exactamente igual (−29.3%) y, peor aún, el filtro penalizó
varios trimestres de recuperación fuerte que se marcaron erróneamente como
"bajistas" (ej. 2019-01, con el top-10 subiendo un +24.7% real, habría
entrado solo al 50%) — el resultado final es peor que no aplicar ningún
filtro (Sharpe 0.55, por debajo incluso del SPY). Una señal de tendencia
trimestral es demasiado lenta para proteger de una caída rápida; si se quiere
protección real hacen falta señales más rápidas (ej. volatilidad implícita,
rebalanceo mensual en vez de trimestral) — no está implementado.

### ⚠️ Aviso: las cifras de arriba se calcularon con un universo sesgado (bug de muestreo)

Todas las tablas anteriores en esta sección (el resultado 2016-2025, el
experimento de posiciones/filtro de régimen, la sensibilidad a costes) se
calcularon con `max_symbols=200`, y se descubrió después que ese parámetro
**no cogía una muestra representativa del S&P 500**, sino sistemáticamente
las primeras ~200 empresas por orden alfabético — ver "Corrección crítica"
más abajo para la causa exacta y el arreglo (ya aplicado). El resto de esta
auditoría (look-ahead, supervivencia a nivel de universo, costes) sigue
siendo metodológicamente correcto — lo que fallaba era la composición de la
muestra, no el mecanismo de cálculo. **El backtest ya se rehizo con el
muestreo corregido — resultado en "Resultado corregido" más abajo.** La
tabla de sensibilidad a costes no se ha vuelto a calcular todavía sobre el
universo corregido (la lección cualitativa — que el margen se estrecha
mucho con costes realistas — probablemente se mantenga, pero la cifra
exacta del punto de equilibrio debería revisarse).

### Resultado corregido (muestreo aleatorio con semilla fija, guard de reciclaje activo)

Mismo periodo (2016-07 a 2025-04, 36 trimestres — uno menos que antes por un
ajuste de fecha de corte, ver nota), mismo `max_symbols=200`, pero con
`_sample_symbols` (aleatorio, semilla 42) en vez del recorte alfabético, y
con el guard de reciclaje de tickers activo:

| Estrategia | Acumulado | Anualizado | Vol. anualizada | Sharpe | Sortino | Máx. drawdown |
|---|---|---|---|---|---|---|
| Top-10 | +397.8% | +19.52% | 20.94% | 0.74 | 1.28 | −27.0% |
| **Top-20** | +362.8% | +18.56% | 19.24% | **0.76** | **1.32** | **−25.4%** |
| Top-30 | +229.4% | +14.16% | 19.87% | 0.51 | 0.83 | −26.4% |
| Top-10 + filtro SMA200 del SPY | +269.8% | +15.64% | 19.47% | 0.60 | 0.96 | −27.0% |
| Universo equal-weight (sin ranking) | +195.4% | +12.79% | 19.86% | 0.44 | 0.67 | −30.5% |
| SPY (cap-weighted) | +210.8% | +13.43% | 17.83% | 0.53 | 0.79 | −23.9% |

Top-10 le gana al universo equal-weight el 72% de los trimestres (antes
59%) y al SPY el 75% (antes 62%).

**La conclusión direccional se mantiene, y de hecho sale más limpia que
antes, no más débil**:

- El universo equal-weight ahora rinde casi exactamente igual que el SPY
  (le gana el 50% de los trimestres, antes 56% con el universo sesgado) —
  justo lo que cabría esperar de una muestra aleatoria representativa del
  índice cap-weighted. Antes, parte de la "ventaja" del equal-weight sobre
  el SPY podía venir del sesgo alfabético, no de un efecto real de
  ponderación; ahora que esa ventaja desaparece casi del todo, la que le
  queda al ranking frente al SPY es más creíble como señal genuina, no como
  artefacto de la muestra.
- **Pasar de 10 a 20 posiciones ahora es una mejora limpia en todos los
  frentes**, no solo en drawdown: Sharpe (0.76 vs 0.74), Sortino (1.32 vs
  1.28) y máximo drawdown (−25.4% vs −27.0%) mejoran los tres a la vez con
  20 posiciones — la recomendación de usar 20 en vez de 10 queda reforzada.
- Top-30 sigue siendo peor en todo (Sharpe 0.51) — diluye demasiado.
- El filtro de SMA200 del SPY **sigue sin reducir el drawdown** (−27.0%,
  idéntico a la base) por la misma razón de siempre: reacciona demasiado
  tarde para una caída rápida como la del COVID. Sigue sin recomendarse tal
  como está planteado.

**Nota sobre los 36 vs 37 periodos**: el rango se cortó en `2025-07-02` en
vez de bien avanzado 2025 por un ajuste de la fecha de fin al relanzar el
script, perdiendo el trimestre 2025-07-01 (un dato ya conocido, no un
problema de cobertura) — diferencia menor, no afecta a las conclusiones.

### Auditoría de sesgos: supervivencia, look-ahead y costes

Cualquier resultado de backtesting tan bueno como el de arriba merece
desconfianza por defecto hasta comprobar los fallos que más lo falsean. Se
auditó el código línea a línea para cada uno, a petición explícita de una
revisión externa muy concreta sobre survivorship bias, look-ahead bias y
costes de fricción:

**Sesgo de supervivencia** — resuelto en el diseño. `universe.get_sp500_constituents_asof(fecha)`
(`src/gabi/universe.py:91-135`) reconstruye la composición real del índice en
cada fecha (`history[history["date"] <= fecha].iloc[-1]`), no usa el universo
de hoy — prueba de ello: al preparar los datos aparecieron decenas de
empresas ya desaparecidas (ABMD, CELG, ANTM, ATVI, BBBY...) precisamente
porque el sistema pidió los componentes reales de esos años. Cuando la fecha
cae fuera del histórico gratuito, la función marca `is_exact=False` y tanto
`multifactor_backtest.run()` como los scripts de este backtest **descartan
ese periodo en vez de usar el universo actual en silencio** (por eso
2025-10 en adelante no aparece en ningún resultado). El matiz que sí queda:
69 de 301 empresas históricas reales no resuelven en el mapeo de tickers de
la SEC (recicladas/deslistadas hace tiempo) y por tanto no pueden puntuarse
esos periodos, aunque sí cuentan en el universo — un sesgo más sutil hacia
"lo que todavía es resoluble", no hacia "lo que sobrevivió en el índice".

**Look-ahead bias** — comprobado línea a línea. `get_value_as_of()`
(`src/gabi/edgar.py:349-361`) filtra `df["filed_date"] <= as_of_date`, donde
`filed_date` es el campo `filed` que devuelve la propia SEC (`src/gabi/edgar.py:308`):
la fecha real en que el 10-K/10-Q se hizo público, no la fecha de cierre del
ejercicio. Si el FY2020 se publicó en febrero de 2021, un `as_of_date` de
enero de 2020 no lo ve. Los precios se truncan igual
(`_price_history_as_of`, `src/gabi/screener_asof.py:81`: `df[df.index <= as_of_date]`),
así que momentum, RSI, SMA, Sharpe y beta reconstruidos para una fecha
pasada tampoco ven precios futuros.

**Costes de fricción** — modelados, pero la primera comparación que se hizo
era optimista sin querer. `_period_returns()` aplica el coste a **todas**
las posiciones, en **todos** los periodos, incluido el SPY de referencia —
es decir, cobraba la misma fricción de rotación trimestral completa a un
inversor pasivo que en la práctica no rota nada. Corrigiendo eso (SPY como
*buy-and-hold* real, coste ≈0, frente a la estrategia con coste creciente):

| Coste por lado | Top-10 anualizado | Sharpe | Brecha vs SPY *buy-and-hold* real |
|---|---|---|---|
| 10 pb (el usado en todo este documento) | +17.70% | 0.69 | +2.81pp |
| 25 pb | +16.29% | 0.62 | +1.41pp |
| **50 pb** | +13.98% | 0.50 | **−0.90pp (pierde)** |
| 100 pb | +9.48% | 0.28 | −5.41pp |

**La ventaja desaparece entre 25 y 50 puntos básicos por lado.** 10pb es una
estimación razonable para grandes capitalizadas líquidas con buena
ejecución, pero no heroica — con spreads más anchos, slippage en el día de
rebalanceo, o empresas menos líquidas del universo, no es descabellado
acercarse a 50pb. Esto no invalida el resultado, pero sí dice con toda
claridad que **el margen de seguridad es más estrecho de lo que sugería la
comparación original**, y que antes de operar esto con dinero real hace
falta medir costes de ejecución reales, no asumirlos.

Falta además un coste real no modelado en absoluto: **la fiscalidad**. Con
rebalanceo trimestral casi todas las plusvalías serían a corto plazo (tipo
marginal, no el reducido de largo plazo) — un descuento adicional que no
aparece en ninguna cifra de este documento y que en una cuenta no protegida
fiscalmente podría por sí solo consumir el margen que queda tras los costes
de ejecución.

**Sobre los factores como probabilidad, no predicción**: el resultado de
2025 (el top-10 perdiendo en 2 de los últimos 3 trimestres reales frente al
SPY, ver arriba) es justo la firma que cabría esperar de una ventaja
estadística pequeña aplicada muchas veces — no la de una máquina de acertar
cada trimestre. Y frente al test de "sospechosamente bueno" (un backtest que
mejora retorno *y* drawdown a la vez suele oler a fuga de información): aquí
el drawdown es *peor* que el del SPY (−29.3% vs −23.9%), lo contrario de esa
firma — coherente con una estrategia concentrada real, no con un resultado
inflado.

### Corrección crítica: el universo de 200 empresas nunca fue representativo

Al comprobar en detalle el sesgo de supervivencia con un caso real (la
quiebra de PG&E, `PCG`, enero de 2019 — sí seguía siendo constituyente real
del S&P 500 en 2018-10-01 según la reconstrucción histórica), se descubrió
que `universe.get_sp500_constituents_asof()` devuelve los símbolos **en
orden alfabético estricto**, y que tanto `multifactor_backtest.run()` como
`required_symbols()` recortaban con `symbols[:max_symbols]` — con
`max_symbols=200` sobre ~500 empresas, **siempre se cogían las primeras ~200
alfabéticamente**, trimestre tras trimestre. Prueba concreta: PG&E está en
la posición 353 de 496 en la composición de 2018-10-01 — nunca entraba en
ningún backtest con `max_symbols=200`, y con ella toda empresa desde
aproximadamente la "N/O" en adelante (Pepsi, Pfizer, Procter & Gamble,
Qualcomm, Starbucks, Target, UnitedHealth, Visa, Walmart, Exxon...), tanto
del ranking top-N como del benchmark "universo equal-weight" con el que se
comparaba. No es un sesgo con lógica económica (como el de supervivencia) —
es puramente accidental, pero afecta a **todos** los resultados numéricos de
esta sección calculados con `max_symbols` fijado (200, 100 o 50, incluido el
primer resultado de 2019).

**Corregido** en `src/gabi/multifactor_backtest.py`: se sustituyó el
recorte `[:max_symbols]` por un muestreo aleatorio con semilla fija
(`random.Random(42).sample(...)`, función `_sample_symbols`) — reproducible
entre llamadas, pero sin sesgo hacia ninguna parte del alfabeto. Afecta
también al selector "Universo: 50/100/500" de 🕰️ Ranking histórico, no solo
a los scripts de este documento. **Ya rehecho — ver "Resultado corregido"
más arriba.**

### Riesgo adicional descubierto: reciclaje de ticker en los precios

Al investigar por qué PG&E no aparecía, se comprobó también si los precios
de empresas que desaparecen del índice siguen reflejando su destino real
(quiebra, exclusión) en vez de desaparecer sin más del dataset — la segunda
pregunta crítica planteada. Resultado mixto:

- **PG&E**: yfinance sí tiene el histórico completo con la caída real
  (−72% real entre finales de octubre de 2018 y principios de febrero de
  2019) — el problema era solo que nunca se pedía (por el bug de arriba).
- **Bed Bath & Beyond (`BBBY`, quiebra y exclusión real en 2023)**: yfinance
  devuelve para ese mismo ticker **cotización "viva" de 2026**, sobre 3-4$
  con volumen normal — la bolsa ha reasignado el símbolo a una empresa
  distinta que no tiene nada que ver con la original. El lado EDGAR/CIK del
  código ya tenía protección explícita contra esto (guarda el `title`
  resuelto para poder detectarlo, ver docstring de `get_cik_for_symbol`),
  pero el lado de precios no tenía ninguna salvaguarda.

**Corregido**: `edgar.get_last_filed_dates(symbols)` (nuevo, en lote) da la
fecha del filing SEC más reciente que tenemos por símbolo. En
`multifactor_backtest._period_returns()`, si una empresa lleva más de 450
días sin presentar nada ante la SEC (una empresa viva presenta un 10-Q como
mínimo cada trimestre) pero el precio de salida cae después de ese hueco, se
trata como no verificable y se descarta ese periodo (`ValueError`, con
mensaje explícito) en vez de usar en silencio lo que devuelva yfinance. Dos
tests nuevos en `tests/test_multifactor_backtest.py` cubren ambos casos
(empresa con filing reciente: se acepta; empresa con hueco largo: se
rechaza).

**Alcance real de esta protección, con honestidad**: solo funciona para
empresas de las que ya tenemos algún histórico en `edgar_facts` (como
PG&E). Para una empresa que **nunca** resolvió CIK en absoluto (como
`BBBY`, que tampoco aparece en el mapeo de tickers de la SEC) no hay fecha
de filing con la que comparar, así que el guard no puede activarse para
ella — en la práctica esto importa poco porque esas mismas empresas ya
quedan excluidas del ranking por el filtro de cobertura mínima de
fundamentales (sin CIK no hay métricas, sin métricas no hay `score_coverage`
suficiente), así que su precio contaminado tampoco llegaba a usarse. El
riesgo real que cierra este arreglo es el más peligroso: una empresa con
historial real y fiable en la base de datos que deja de filtrar en algún
punto y cuyo ticker se recicla después — ese caso sí podía colarse en
silencio antes de esta corrección.

### Por qué no se pudo ampliar a 2010 o antes

Se intentó extender el backtest a 2010-2024 para incluir más ciclos de
mercado. El resultado confirma con datos reales lo que predice el calendario
regulatorio: la SEC no exigió XBRL estructurado (los datos que necesita el
ranking para reconstruirse en una fecha pasada) hasta 2009, y la cobertura
tardó años en madurar incluso después:

| Fecha | Empresas con cobertura suficiente (de 200) |
|---|---|
| Ene 2010 | 7 |
| Ene 2011 | 64 |
| Ene 2013 | 105 |
| Ene 2015 | 112 |
| Abr 2016 | 118 |
| **Jul 2016** | **122 (primer trimestre que supera el umbral del 60%)** |

**Los 24 trimestres de 2010 a mediados de 2016 se saltan enteros** por no
llegar nunca al 60% de cobertura del universo — no es un fallo de caché ni
de fetching, es que la mayoría de empresas medianas del S&P 500 de esa época
simplemente no tenían fundamentales en formato estructurado todavía. 2000 o
2005 son directamente inviables: en 2000 y 2005 no existía ninguna
obligación de reportar XBRL, así que no hay datos que descargar por muy
atrás que se intente. El backtest fiable con esta fuente de datos empieza,
como mucho, a mediados de 2016.

### Checklist de sesgos de backtesting — auditoría completa

Revisión explícita contra los seis errores más habituales en backtesting casero
(supervivencia, look-ahead, *multiple testing*, costes, *data snooping*, validación
temporal): supervivencia y look-ahead están resueltos con evidencia (ver arriba);
costes están modelados pero con matices; *multiple testing*, *data snooping* y
validación temporal **no** lo estaban — toda la exploración de esta sección se hizo
mirando el mismo rango histórico una y otra vez, sin corrección estadística ni tramo
reservado. Ver **[`HIPOTESIS_CONGELADA.md`](HIPOTESIS_CONGELADA.md)**: la configuración
concreta que se cree buena, congelada por escrito antes de tener ningún dato nuevo con
el que validarla — es la única forma honesta de comprobar si de verdad funciona, en vez
de seguir ajustando sobre el mismo pasado. También incluye un contraste externo con las
series académicas de factores de Kenneth French (`src/gabi/academic_factors.py`,
disponible en 🕰️ Ranking histórico): el 91.5% del retorno de la estrategia ya lo explican
seis factores de mercado conocidos, y el alfa restante, aunque positivo, no llega al
umbral de significancia estadística habitual.

### Hipótesis descongelada — exploración activa de turnover y frecuencia de rebalanceo

`HIPOTESIS_CONGELADA.md` se descongeló el 2026-09-18 a petición explícita del usuario,
que prefiere seguir mejorando el backtest activamente en vez de esperar a la validación
prospectiva — decisión legítima, documentada con transparencia en el propio archivo (que
se conserva como registro histórico de lo que se intentó). A partir de aquí, cualquier
hallazgo vuelve a estar sujeto al mismo riesgo de *multiple testing*/*data snooping* que
motivó congelarla la primera vez — tenerlo presente al leer lo siguiente.

**Banda de permanencia para reducir turnover (`buffer_multiplier` en
`multifactor_backtest.run()`)**: probado a 1.3x/1.5x/2.0x contra el top-20 estricto, en
10/25/50 puntos básicos de coste, con el ahorro de coste real de las posiciones mantenidas
correctamente modelado (`held_symbols` en `_period_returns()`). **Resultado: no compensa
a ningún nivel de coste probado** — reduce turnover (63.1%→51-57%) pero pierde más en
calidad de selección de lo que ahorra en coste, en los tres niveles. Descartado.

**Frecuencia de rebalanceo (trimestral vs semestral vs anual)**, mismo top-20, 2016-2025:

| Frecuencia | Coste | Turnover | Sharpe | Sortino | Anualizado | Max DD | Periodos |
|---|---|---|---|---|---|---|---|
| Trimestral | 10/25/50pb | 63.1% | 0.77/0.73/0.65 | 1.36/1.26/1.11 | +18.9%/+18.0%/+16.5% | −25.4% a −25.8% | 36 |
| Semestral | 10/25/50pb | 72.4% | 0.96/0.92/0.87 | 2.02/1.92/1.76 | +17.8%/+17.3%/+16.4% | −16.4% a −16.7% | 18 |
| Anual | 10/25/50pb | 80.0% | 0.90/0.88/0.85 | 3.05/2.92/2.71 | +15.2%/+14.9%/+14.5% | −7.0% a −7.6% | 9 |

A primera vista, semestral y anual parecen mucho mejores en riesgo ajustado. Dos
verificaciones adicionales, ambas importantes, **cambian la conclusión por completo**:

1. **Contraste con Kenneth French sobre la serie semestral**: R²=0.926 (más explicado por
   factores conocidos que el trimestral, no menos), alfa anualizado +1.55% con t-stat 0.62
   (más débil que el trimestral: +3.85% con t-stat 1.61). La mejora de Sharpe de la tabla
   de arriba **no venía de más alfa genuino — venía de una beta de Calidad (RMW) mucho más
   fuerte y esta vez sí significativa** (0.618, t=2.75, vs 0.264 del trimestral).
2. **El drawdown de la tabla de arriba estaba mal calculado — confirmado, no solo
   sospechado**. `max_drawdown` se calculaba sobre `periods["capital"]`, el capital SOLO en
   las fechas de rebalanceo — con rebalanceos más espaciados, una caída y recuperación
   completa *dentro* de un periodo (el crash de marzo de 2020 dentro de un periodo semestral
   o anual que termina recuperado) era invisible para ese cálculo. Nuevas
   `multifactor_backtest.daily_capital_curve()` y `daily_risk_metrics()` reconstruyen una
   curva de capital DIARIA (ancladas exactamente a los mismos retornos por periodo ya
   validados, solo revelan el camino real dentro de cada tramo) para poder comparar de
   verdad entre frecuencias distintas. **Resultado real sobre el mismo backtest, medido
   correctamente:**

   | Frecuencia | Sharpe (diario, comparable) | Sortino (diario) | Max DD (diario) |
   |---|---|---|---|
   | **Trimestral** | **0.74** | 1.04 | −37.2% |
   | Semestral | 0.69 | 0.95 | −37.2% |
   | Anual | 0.57 | 0.80 | −35.4% |

   **Los tres sufrieron prácticamente la misma caída real durante el COVID** (−35% a
   −37%) — es una caída de mercado generalizada, no algo de lo que protegiera rebalancear
   menos. Lo que antes parecía "el semestral/anual protege mejor" nunca fue protección
   real: era, literalmente, no mirar la cuenta durante la caída y fijarse solo en cómo
   había quedado meses después, ya recuperada. **Con la métrica correcta, es el
   trimestral el que tiene mejor Sharpe** — rebalancear más a menudo permite refrescar
   hacia mejores candidatas con más frecuencia, y ese beneficio de selección pesa más que
   el coste de rotación adicional, al menos a 10pb. **La recomendación de pasar a
   rebalanceo semestral queda retirada** — se apoyaba en una métrica de riesgo defectuosa.

   Verificado que `daily_capital_curve` reproduce exactamente los mismos retornos totales
   ya validados con el cálculo por periodos (+374.9% trimestral, +337.2% semestral,
   +257.1% anual) — el único cambio es la visibilidad del camino diario dentro de cada
   tramo, no el retorno final.

### Costes reales del bróker (eToro): calibración y por qué el backtest NO incluye la conversión de divisa

GABI es de uso personal, y el bróker real del usuario es eToro. Se calibraron los costes
contra dos fuentes reales: el extracto oficial de cuenta (`Posiciones cerradas`,
`Actividad de la cuenta`, `Resumen de la cuenta`, abril-septiembre 2026) y un TSV de
movimientos bancarios, para poder separar depósitos hechos con tarjeta de los hechos con
transferencia. Cada cifra de abajo se verificó transacción a transacción contra esas
fuentes (no se tomó de memoria ni de un análisis externo sin comprobar) — módulo
`src/gabi/broker_costs.py`, tests en `tests/test_broker_costs.py`.

**Costes de operar (abrir/cerrar una posición), verificados sobre 61 cargos reales:**

| Concepto | Importe | Evidencia |
|---|---|---|
| Acción/ETF (EE.UU. y la mayoría de mercados) | 1.00 USD por lado, fijo | 56/61 cargos reales |
| Acción de Hong Kong | 2.00 USD por lado, fijo | 1/61 cargos reales |
| Criptomoneda | ~1.00% del importe, por lado | 4/61 cargos, 1.000% exacto |
| SDRT (compra de acciones del Reino Unido) | 0.50% | impuesto, no comisión del bróker |

**Costes de depositar (conversión EUR→USD al meter dinero nuevo desde el banco):**

| Método | Coste efectivo | Evidencia |
|---|---|---|
| Transferencia bancaria | ~0.60% | 24+ conversiones reales, verificadas cruzando fecha/importe del TSV bancario contra el extracto de eToro |
| Tarjeta de crédito/débito | ~1.30% | 4/4 depósitos con tarjeta, 1.294%-1.318% |

Nota aparte (no usada como valor por defecto, solo documentada): los dos primeros
depósitos de la cuenta (abril de 2026) pagaron ~0.75% en vez del ~0.60% habitual —
posible tarifa de arranque o de tramo bajo de saldo, no confirmado que sea la tarifa
vigente.

**Decisión de diseño — el backtest (`multifactor_backtest.py`) solo usa el coste de
operar, nunca el de depositar.** Un rebalanceo del backtest simula vender una empresa y
comprar otra *dentro* de la cuenta — dinero que ya está en eToro moviéndose entre
posiciones, exactamente lo que cobra el coste de operar. El coste de depositar es un
evento distinto: EUR saliendo del banco y convirtiéndose a USD al entrar en eToro, que
ocurre una vez por aportación real, no una vez por rebalanceo. Cobrarlo en cada periodo
del backtest sería un error de categoría — inflaría el coste modelado sin representar
ningún movimiento de dinero real que el backtest esté simulando, ya que el capital que se
rota trimestre a trimestre no vuelve a cruzar la frontera banco↔eToro en cada rotación
(tanto si viene de una aportación reciente como si ya llevaba tiempo invertido: rotarlo
sigue siendo mover dinero entre empresas, no traerlo de fuera).

El coste de depositar sí importa, pero en otro sitio: en el coste real de vida de la
cartera del usuario (10.000€ ya invertidos en septiembre de 2026, +~700€/mes de media,
depositados históricamente con tarjeta), no en la mecánica del backtest de selección de
empresas. Por eso vive en Carteras Simuladas (🧪, que sí modela capital entrando a la
cuenta) y en este documento, no como parámetro de `multifactor_backtest.run()`.

**El coste de operar SÍ es sensible al tamaño de posición** (a diferencia de un `cost_bps`
plano): 1 USD es un 0.18% sobre una posición de 550 USD pero solo un 0.01% sobre una de
10.000 USD, porque eToro cobra un importe fijo, no un porcentaje.
`broker_costs.effective_trade_cost_bps(position_size_usd)` hace esa conversión para un
tamaño de posición concreto — la página 🕰️ Ranking histórico tiene una calculadora que,
dado el capital total y el nº de posiciones del usuario, muestra el coste por lado
equivalente para copiarlo en "Coste por lado (pb)". Con la situación real del usuario a
día de hoy (~10.000€ entre 20 posiciones ≈ 500€/posición), el coste real de operar
equivale a **~18-20 puntos básicos por lado** — dentro del rango 10-25pb ya explorado en
la tabla de arriba, más cerca del extremo alto que del optimista 10pb usado por defecto.

## Insiders (SEC Form 4)

`src/gabi/insider.py` descarga y guarda las operaciones de directivos,
consejeros y accionistas >10% desde los Form 4 de SEC EDGAR (Section 16) —
gratis, sin API key. Es la señal de "qué sabe la dirección que el mercado no
sabe todavía" que faltaba (ninguna otra fuente integrada la da). Se muestra
en 🔍 Ficha de empresa: compras/ventas en mercado abierto de los últimos 6
meses, cuántos insiders distintos compraron, valor neto comprado-vendido, y
si las compras son de un plan 10b5-1 preprogramado (mucho menos informativas
que una compra discrecional decidida ahora). Verificado con los Form 4 reales
de Apple — parsea correctamente nombre, cargo, código de operación, acciones,
precio y si hay un plan 10b5-1 detectado por las notas al pie del filing.

Solo cuentan como señal las compras/ventas en mercado abierto (códigos P/S);
concesiones, ejercicios de opciones y retenciones fiscales se guardan pero no
se cuentan como "convicción". De momento es **informativo, no entra en el
Composite Score** — mismo criterio que con el resto de bloques nuevos: antes
de dejar que una señal puntúe, hay que ver si aporta algo con datos reales.

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

**Splits y dividendos:** yfinance devuelve el precio siempre ajustado por splits
futuros. La descarga usa `auto_adjust=False` para guardar `Close` (ajustado por
splits) y `Adj Close` (ajustado además por dividendos). Los múltiplos históricos
usan `Close`; la evaluación de retornos usa `Adj Close`. La caché anterior debe
actualizarse antes de reconstruir múltiplos. El nº de acciones de SEC EDGAR es
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
- Ampliar el backtest point-in-time con validación de identidad de empresas,
  costes reales de ejecución e histórico completo. Solo después, modelos
  de Machine Learning interpretables (regresión, Random Forest, XGBoost) con
  walk-forward validation — nunca mezclando aleatoriamente pasado y futuro.
