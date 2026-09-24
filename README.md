# GABI — Screener de acciones (fundamentales + momentum)

Herramienta de uso **personal y educativo** para analizar empresas del S&P 500
combinando métricas fundamentales (valor y calidad) con señales técnicas de
momentum, con el objetivo de identificar candidatas a entrar en una fase
alcista en un horizonte de 6-12 meses, y sobre todo **entender por qué**.

> ⚠️ **No es asesoramiento financiero.** Los datos vienen de fuentes gratuitas
> (Yahoo Finance, SEC EDGAR, FRED) y pueden tener errores, retraso o estar
> incompletos. Verifica siempre por tu cuenta antes de invertir.

## Calidad y trazabilidad de datos

La identidad persistente por CIK, los alias con vigencia, la migración aditiva
de SQLite y la cobertura histórica medida se describen en
[Identidad de entidades](docs/entity-identity.md). Por defecto, el ranking
histórico sigue leyendo de la caché legacy por ticker para los símbolos sin
alias migrado (todos, hasta completar la migración) — `identity_status` marca
cada fila como resuelta, ambigua o sin acreditar, visible en vez de oculto.
Activar identidad estricta (`strict_identity=True`) exige datos atribuidos a
una entidad acreditada y deja ausentes los que no la tengan; solo tiene
sentido tras migrar y atribuir `data/gabi.db`.

La página **🩺 Calidad de los datos** consulta solo la caché local. Muestra
cobertura y frescura de Yahoo, SEC EDGAR, FRED y Entity Master, porcentaje
completo por bloque del score, CIK resuelto, últimos filings y errores recientes.
El detalle permite elegir la fecha de referencia del sector y distingue
point-in-time, aproximado y ausente. El estado global sigue degradado mientras
existan las limitaciones estructurales indicadas, aunque las descargas sean recientes.

Screener y Ranking histórico permiten ajustar el umbral de cobertura en la
barra lateral. Los backtests V1/V2 conservan el diagnóstico por fecha y lo
guardan con el experimento del Research Lab.

El `data_fingerprint` v2 usa SHA-256 sobre contenido ordenado de precios,
benchmark, splits, fundamentales, XBRL, sectores, CIK, FRED y snapshots del
universo. Detecta correcciones históricas aunque no cambie la última fecha.
La UI lo captura al terminar el backtest y conserva esa huella al registrarlo;
las entradas manuales permiten pegar la huella del run original. La versión
del entorno y el commit se registran por separado. Una huella identifica la
caché, pero **no archiva los datos**: reproducir un run exige conservar también
su caché y configuración. No se equiparan las huellas antiguas con las v2.

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

Requiere [uv](https://docs.astral.sh/uv/) (gestor de paquetes/entornos). Las
versiones exactas de cada dependencia quedan fijadas en `uv.lock`, así que dos
instalaciones en fechas distintas usan siempre las mismas versiones de
pandas, numpy, yfinance, etc.

En Windows, instala `uv` una vez con PowerShell (no hace falta Python
preinstalado, `uv` también gestiona la versión de Python):

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Y luego, en el proyecto:

```bash
uv sync
```

Esto crea `.venv/` e instala dependencias + dependencias de desarrollo
(pytest, ruff, mypy). Para actualizar versiones deliberadamente: `uv lock --upgrade`.

## Uso

```bash
uv run streamlit run app/streamlit_app.py
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
uv run pytest
uv run ruff check .     # linting
uv run mypy src/gabi    # type checking
```

Los tres se ejecutan también en CI (GitHub Actions) en cada push/PR a
`main`/`develop`, contra las versiones exactas fijadas en `uv.lock`.

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
- Pasar de 10 a 20 posiciones mejora los tres frentes a la vez (Sharpe 0.76
  vs 0.74, Sortino 1.32 vs 1.28, máx. drawdown −25.4% vs −27.0%) — pero
  **el gap de Sharpe (0.02) es muchísimo menor que el error estándar
  esperable con ~9 años de datos (~0.36, ver más abajo)**, así que no se
  puede llamar "mejora limpia" en sentido estadístico. Se mantiene 20 como
  valor por defecto porque el drawdown algo menor es deseable y no cuesta
  nada de retorno esperado, no porque la comparación de Sharpe la respalde.
- Top-30 sigue siendo claramente peor (Sharpe 0.51) — esa diferencia sí es
  mayor que el ruido de muestreo típico.
- El filtro de SMA200 del SPY **sigue sin reducir el drawdown** (−27.0%,
  idéntico a la base) por la misma razón de siempre: reacciona demasiado
  tarde para una caída rápida como la del COVID. Sigue sin recomendarse tal
  como está planteado.

**Nota sobre los 36 vs 37 periodos**: el rango se cortó en `2025-07-02` en
vez de bien avanzado 2025 por un ajuste de la fecha de fin al relanzar el
script, perdiendo el trimestre 2025-07-01 (un dato ya conocido, no un
problema de cobertura) — diferencia menor, no afecta a las conclusiones.

**⚠️ Aviso añadido después, con dos problemas de medida más (ver sección
"Hipótesis descongelada" más abajo para el detalle y la corrección
numérica completa)**: (1) el máximo drawdown de esta tabla se calculó
sobre el capital SOLO en fechas de rebalanceo (`periods["capital"]`), el
mismo defecto de medida que infravaloró el drawdown real en la comparación
de frecuencias de rebalanceo (−25.4% medido así, pero se comprobó después
que el drawdown diario real de una configuración equivalente ronda −37%);
(2) ninguna de las diferencias de Sharpe de esta tabla se contrastó nunca
contra su error estándar de muestreo. Los números de esta tabla, tal cual,
probablemente subestiman el riesgo real y sobreinterpretan diferencias
pequeñas — tratarlos como orientativos, no como la medición más fiable
disponible.

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
disponible en 🕰️ Ranking histórico): el 91.5% de la varianza del retorno de la estrategia ya lo explican
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
   (más débil que el trimestral: +3.85% con t-stat 1.61). **Estos t-stats históricos
   son OLS homocedásticos, sin corrección HAC**; la regresión actual usa Newey-West
   y anualiza según la frecuencia real. Ver [metodología y recálculo](docs/academic-factors-hac.md).
   La comparación histórica apuntaba a una beta de Calidad (RMW) mayor
   (0.618, t OLS=2.75, vs 0.264 del trimestral), sin evidencia de más alfa.
   La significancia de esa beta también debe revisarse con HAC.
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
   | Trimestral | 0.74 | 1.04 | −37.2% |
   | Semestral | 0.69 | 0.95 | −37.2% |
   | Anual | 0.57 | 0.80 | −35.4% |

   (Ver la corrección justo debajo de la tabla — estas diferencias no son estadísticamente
   significativas; no interpretar el trimestral como "el que gana".)

   **Los tres sufrieron prácticamente la misma caída real durante el COVID** (−35% a
   −37%) — es una caída de mercado generalizada, no algo de lo que protegiera rebalancear
   menos. Lo que antes parecía "el semestral/anual protege mejor" nunca fue protección
   real: era, literalmente, no mirar la cuenta durante la caída y fijarse solo en cómo
   había quedado meses después, ya recuperada. **La recomendación de pasar a rebalanceo
   semestral queda retirada** — se apoyaba en una métrica de riesgo defectuosa.

   Verificado que `daily_capital_curve` reproduce exactamente los mismos retornos totales
   ya validados con el cálculo por periodos (+374.9% trimestral, +337.2% semestral,
   +257.1% anual) — el único cambio es la visibilidad del camino diario dentro de cada
   tramo, no el retorno final.

   **⚠️ Corrección — "el trimestral gana" tampoco es una conclusión sólida, es el mismo
   error en sentido contrario.** Con solo ~9 años de datos, el error estándar de un
   Sharpe estimado así (`sharpe_standard_error`, fórmula de Lo 2002:
   `√((1 + Sharpe²/2) / años)`) ronda **±0.36-0.38** para los tres Sharpes de la tabla —
   ver la cifra exacta, recalculada, en la verificación final más abajo. La diferencia
   entre trimestral y anual es una fracción de un error estándar, indistinguible del
   ruido de muestreo con esta cantidad de historia. La lectura honesta no es "el
   trimestral es mejor", es que **la frecuencia de rebalanceo no cambia gran cosa dentro
   de este rango de datos** — la elección de quedarse con trimestral es razonable porque
   ya es la que se usa y es operativamente más simple (más oportunidades de refrescar
   hacia mejores candidatas, coste ya medido y asumible a 10-25pb), no porque haya
   "ganado" una comparación estadísticamente significativa. Ver
   `multifactor_backtest.sharpe_standard_error()` — a partir de ahora, cualquier
   comparación de Sharpe entre variantes en este documento debe acompañarse de su error
   estándar antes de declarar una ganadora.

### Verificación final: un tercer problema de medida (cobertura del universo) y comparación honesta contra el SPY

Al intentar reproducir la tabla de arriba de forma limpia (con `sharpe_standard_error` y
una comparación de drawdown contra el SPY con la MISMA metodología de curva diaria, dos
peticiones explícitas del usuario tras revisar este documento) se descubrió un **tercer
problema real, independiente de los dos anteriores**: `multifactor_backtest.run()` con
sus parámetros por defecto (`min_universe_coverage=0.7`) solo conseguía reconstruir 13 de
los 36 trimestres del rango 2016-2025 — **todo 2016-2021, incluido el crash de marzo de
2020, se saltaba en silencio**, y el resto de este documento nunca lo mencionó porque las
cifras "de 36 periodos" se habían generado con un script aparte, con un umbral de
cobertura distinto (no el `run()` estándar que usa el botón de la interfaz).

La causa: de los ~640 símbolos distintos que hacen falta para cubrir el rango completo,
**100 (≈16%) nunca resuelven CIK en SEC EDGAR** — son empresas realmente deslistadas o
adquiridas antes de 2022 (ABC, ANTM, ATVI, CELG, BBBY, RTN, UTX, JEC, MYL... la lista
completa es mucho más larga) que sí formaban parte del S&P 500 en su momento, pero
`company_tickers.json` de la SEC solo mapea registrantes **activos hoy**, no históricos.
Eso limita la cobertura alcanzable de cualquier trimestre anterior a 2022 a un techo
estructural de ~57-69% del universo muestreado — no es que esos periodos tengan peor
calidad de datos, es que ese es el máximo posible con esta fuente gratuita. Con el 0.7
por defecto, ese techo caía justo por debajo del umbral y el periodo entero desaparecía.

**Arreglado**: `min_universe_coverage` por defecto pasa de 0.7 a **0.5** (`multifactor_backtest.run()`,
ver su docstring) — recupera los 36/36 trimestres sin dejar pasar periodos realmente
vacíos (comprobado). Esto es un límite de origen de datos conocido y documentado, no un
sesgo oculto: las empresas no resueltas simplemente nunca pueden entrar en el ranking en
los periodos anteriores a 2022, así que sí introducen un sesgo de "solo lo que hoy sigue
siendo fácil de mapear" adicional al de supervivencia de índice (que ese sí está
corregido) — pendiente de una mejora futura (búsqueda por nombre en vez de solo por
ticker actual) si se quiere cerrar del todo.

**Con los 36/18/9 periodos reales, cobertura completa, y calculando por fin Sharpe/Sortino/
drawdown/SE con exactamente la misma curva diaria para la estrategia y para el SPY**
(`daily_benchmark_curve`, nueva):

| Frecuencia | Sharpe estrategia (±SE) | Sharpe SPY | Sortino estrategia | Max DD estrategia | Max DD SPY | Turnover |
|---|---|---|---|---|---|---|
| Trimestral | 0.71 ± 0.37 | 0.56 | 1.00 | −37.8% | −33.7% | 63.0% |
| Semestral | 0.68 ± 0.37 | 0.56 | 0.95 | −37.8% | −33.7% | 74.4% |
| Anual | 0.61 ± 0.36 | 0.56 | 0.85 | −33.2% | −33.7% | 81.3% |

**Lo que esto dice, con el mismo cuidado de no sobreinterpretar que llevó a las dos
correcciones anteriores**:

- **Entre frecuencias, sigue sin haber diferencia significativa** (0.71 vs 0.61 es una
  fracción de un SE de ±0.37) — se confirma la conclusión de la sección anterior con
  datos ahora completos y reproducibles, no solo con una aproximación.
- **Frente al SPY, la estrategia gana en Sharpe en las tres frecuencias, de forma
  consistente** (0.71/0.68/0.61 vs 0.56 del propio SPY) — esto es un patrón más robusto
  que "trimestral gana a anual", porque se repite en las tres variantes en vez de
  depender de cuál se mire. Aun así, el margen (0.05 a 0.15) sigue siendo pequeño frente
  al SE individual de cada serie (~0.36-0.37); no se ha hecho el test correcto para
  series correlacionadas (las dos comparten buena parte del mismo riesgo de mercado, así
  que la incertidumbre real de la diferencia es probablemente menor que sumar los dos SE
  como si fueran independientes) — tratar esto como una señal a favor de la estrategia,
  no como una certeza estadística confirmada.
- **El drawdown SÍ muestra algo real y antes invisible**: con rebalanceo trimestral o
  semestral, la estrategia cae más que el SPY en el mismo pánico (−37.8% vs −33.7%, 4.1
  puntos peor) — concentrar en 20 posiciones sí añade riesgo a la baja frente al índice
  completo, coherente con lo ya visto en "Segundo resultado" (10 posiciones cayó más que
  el universo completo en el COVID). Con rebalanceo **anual**, en cambio, el drawdown
  queda prácticamente igual al del SPY (−33.2% vs −33.7%) — la cartera de enero de 2020
  (fijada un año entero) resultó, por esta vez, no más concentrada en riesgo de caída que
  el propio índice. No hay base para generalizar esto como "el anual protege" (un solo
  episodio de mercado, y ya se vio que "el anual gana" fue un espejismo la primera vez) —
  se documenta como lo que es: una observación puntual de este episodio concreto, útil
  para no asumir que más posiciones/más rotación siempre reduce el riesgo de caída.
- **La banda de permanencia (`buffer_multiplier`) también se re-verificó con curva
  diaria y cobertura completa** (36/36 periodos, top-20 trimestral, 1.5x, 10pb): Sharpe
  diario 0.66 frente a 0.71 sin banda, drawdown prácticamente igual (−37.7% vs −37.8%) —
  **confirma la conclusión de "descartado"** del principio de esta sección con datos
  ahora completos, no solo con el rango parcial que se había probado hasta ahora.

Reproducible con `multifactor_backtest.run(..., min_universe_coverage=0.5)` para cada
frecuencia, `daily_capital_curve`/`daily_benchmark_curve`/`daily_risk_metrics` sobre el
resultado, y `sharpe_standard_error(sharpe, years)` sobre cada Sharpe diario.

### Benchmark ajustado por beta y factores

**2026-09-22, issue #16.** Se añaden referencias `RF + beta*(SPY−RF)` y
`RF + suma(beta_j*factor_j)` para FF5+Momentum, excluyendo siempre el alfa.
Ranking histórico V1 y Research Lab muestran curvas comparables, exposiciones
y descargas. La beta SPY del recálculo es **1,035**, sin fijar el 0,97 histórico.

Se distingue atribución sobre toda la muestra de estimación expansiva con
18 trimestres mínimos y uno de embargo. En los 17 trimestres evaluables del
segundo protocolo, la estrategia da CAGR **14,66%**, frente a **13,98%** del
SPY ajustado y **15,27%** del benchmark multifactor. Las diferencias de
**+0,68 y −0,61 puntos/año** no son alfa de regresión ni prueba de selección.
Los factores revisados y la exploración previa impiden llamar a este ejercicio
validación prospectiva; la financiación y replicación son idealizadas.

[Informe, curvas e inputs reproducibles](docs/factor-benchmark/README.md).

### Riesgo de cola: VaR, Expected Shortfall y momentos

**2026-09-22, issue #15.** `portfolio_metrics.py` incorpora VaR y ES/CVaR
históricos al 95%/99%, asimetría y exceso de curtosis. Están disponibles en
Ranking histórico V1/V2, Portfolio Lab y las series guardadas en Research Lab.
Se muestra siempre el horizonte: un retorno trimestral no se convierte en
riesgo diario ni se anualiza el ES con raíz del tiempo.

Aplicado a los 36 trimestres del Top-20 reconstruido: VaR95 **12,06%**, ES95
**18,65%**, VaR99/ES99 **23,92%**; asimetría **−0,229**, exceso de curtosis
**1,578**. Son pérdidas positivas. La cola al 99% equivale a 0,36 observaciones:
el resultado es la peor pérdida observada, sin resolución suficiente para
caracterizar ese extremo. Se conservan resultados de las 24 configuraciones.

[Método, límites y reproducción](docs/tail-risk.md) ·
[Resultados y procedencia](docs/tail-risk-audit.json).

### Estabilidad temporal de alfa y betas

**2026-09-22, issue #13.** El recálculo HAC de 36 trimestres se ha dividido
en mitades cronológicas y 51 ventanas móviles de 4/5/6 años. El alfa anualizado
es −2,91% en la primera mitad y +2,65% en la segunda (t HAC −0,83 y 0,64);
en ventanas de cuatro años oscila entre −5,49% y +9,16%. También cambian las
betas, con incertidumbre amplia: no se demuestra una ruptura estadística.

2018, COVID 2020, tipos 2022 y rally 2023–2024 tienen muy pocos trimestres
para estimar seis betas y alfa por separado. Se publica su atribución con
betas globales y la sensibilidad de coeficientes al excluir cada episodio.
2023–2024 resta contribución ajustada; 2021 y 2019 explican aproximadamente
el 51% y 31% de la suma ajustada neta. Estas cifras son una descomposición
in-sample, no alfas locales ni retornos compuestos.

[Informe, metodología y datos](docs/factor-stability/README.md). Research Lab
muestra gráficos interactivos e intervalos HAC; Ranking histórico permite
repetir el diagnóstico del backtest trimestral actual. Se reproduce sin red
con `uv run python -m gabi.factor_stability`. Sigue pendiente la estabilidad
por régimen de las permutaciones y perturbaciones de pesos originales, cuyos
inputs completos no se conservaron. El turnover agregado no demuestra decay.

### Auditoría retroactiva de *multiple testing*: matriz de los ensayos recuperables

**Actualizada el 2026-09-22, issue #12.** La auditoría ahora conserva una matriz
reproducible de **36 trimestres × 24 ensayos documentados**, no solo métricas
resumen ni la serie elegida. Usa un snapshot SQLite consistente, N=200 por
fecha, semilla 42, el motor V1 actual y el rango 2016-07 a 2025-07.

La familia principal contiene nueve variantes a coste fijo de 10 pb:
Top-10/20/30, filtro SMA200 del SPY sobre Top-10, bandas 1.3/1.5/2.0 sobre
Top-20 y rebalanceo semestral/anual. Los otros quince ensayos son sensibilidad
a costes documentada, no quince estrategias independientes.

| Comparación | PBO (6 bloques, 20 particiones) | DSR del Top-20 |
|---|---:|---:|
| 9 variantes a coste fijo | **10,0%** | **94,08%** |
| 24 ensayos, incluidos costes | **10,0%** | **93,29%** |

Todas las carteras se observan sobre la misma rejilla trimestral con precios
reales, incluso cuando rebalancean semestral o anualmente. El Sharpe usado para
PBO/DSR es media aritmética de excesos/desviación muestral, no CAGR/volatilidad;
el Top-20 da 0.7367. Se conservan sensibilidades al número de bloques y de ensayos.

**Alcance parcial:** no se recuperaron los vectores completos de las
perturbaciones de pesos ni todos los ensayos de factores individuales/versiones
anteriores. PBO evalúa selección por Sharpe, no la decisión histórica conjunta
con drawdown. DSR usa N nominal en variantes muy correlacionadas y no alcanza
el 95%. Esto no valida prospectivamente la estrategia ni corrige con garantías
todo el proceso histórico de búsqueda.

Esta medición sustituye la lectura anterior (experimento #10: N=100, 8
variantes, DSR≈0.83 y PBO≈0.40 sobre 6 trimestrales), cuyo DSR mezclaba
frecuencias y usaba un Sharpe basado en CAGR. Las diferencias no se deben
exclusivamente al número de ensayos: cambian también universo, convención de
Sharpe y muestra comparable. El experimento antiguo se conserva como registro.

[Informe y reproducción](docs/overfitting-audit/README.md) ·
[Matriz de retornos](docs/overfitting-audit/returns.csv) ·
[Resultados y procedencia](docs/overfitting-audit/audit.json).
Las 24 series quedan registradas en Research Lab como RESEARCH; la app
muestra el informe verificado y permite descargar los artefactos.
Para repetir solo el cálculo estadístico:
`uv run python -m gabi.overfitting_audit --analyze-only`.

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

## GABI V2 — Paso 1: motor de backtest con contabilidad real de cartera

`HIPOTESIS_CONGELADA.md` y todo el histórico de backtesting de arriba se generaron con
`multifactor_backtest.py` (a partir de aquí, **V1**), que **no simula una cartera real**:
cada rebalanceo calcula el retorno como la media simple de `(precio_salida/precio_entrada)
* factor_coste`, con el coste aplicado sobre el 100% de cada posición cada trimestre — se
mantuviera o no — y también sobre el SPY (que debería comprarse una vez y mantenerse, no
rotarse cada trimestre). El usuario, revisando este documento, señaló ambos fallos con
precisión y pidió un motor nuevo, más riguroso, como primer paso de una "V2" — manteniendo
V1/`HIPOTESIS_CONGELADA.md` intactos y reproducibles tal cual (quedan como versión
archivada). Ese motor nuevo es **`src/gabi/portfolio_backtest.py`** +
**`src/gabi/portfolio_metrics.py`** (tests en `tests/test_portfolio_backtest.py` y
`tests/test_portfolio_metrics.py`).

**Qué hace distinto**, reutilizando la misma convención de coste ya validada en
`sim_portfolios.py` (Carteras Simuladas — comisión fija en dólares + spread proporcional,
calibrada en `broker_costs.py`) en vez de inventar un modelo nuevo:

- **Contabilidad real por acciones + caja**, no un % agregado. En cada rebalanceo se
  clasifica cada símbolo en `held` (se mantiene), `sold` (sale) o `bought` (entra nueva):
  `sold`/`bought` pagan coste real sobre el 100% de su importe (operación real); `held`
  solo paga sobre la **variación de peso** — el ajuste para volver al peso objetivo
  equiponderado tras el movimiento de precio del trimestre — nunca sobre el 100% de una
  posición que no se ha tocado. Esto es lo que V1 no podía representar (con o sin el
  `held_symbols` de coste cero añadido antes en esta sesión: cero coste para lo mantenido
  tampoco es correcto si el peso ha derivado).
- **SPY como comprar-y-mantener de verdad** (`buy_and_hold_curve`): coste real de entrada
  una sola vez, nunca más — corrige directamente el fallo señalado.
- **Curva NAV diaria genuina** (`_daily_segment`): walk-forward día a día valorando
  `caja + Σ(acciones × adj_close)`, igual que `sim_portfolios.portfolio_history()` — no
  una curva agregada reescalada a posteriori. Además, a diferencia de V1, un periodo
  saltado por falta de cobertura ya no deja un hueco en la curva: la cartera sigue
  flotando con lo que ya tenía en vez de desaparecer del análisis.
- **Métricas nuevas** (`portfolio_metrics.py`, no existían en `risk.py` ni en V1): Calmar,
  tiempo de recuperación, beta, tracking error, Information Ratio, capture ratios
  upside/downside, Sharpe rodante.

### Comparación real V1 vs V2, mismo rango exacto (2016-07 a 2025-07, top-20, trimestral, 36/36 periodos)

| | V1 (coste 10pb round-trip, SPY rotado) | V2 (1 USD + 10pb spread, SPY buy-and-hold) |
|---|---|---|
| Retorno total estrategia | +356.4% | +347.3% |
| Retorno total SPY | +233.2% | **+245.7%** |
| Turnover medio | 63.0% (solo nombres que cambian, 1 lado) | **127.4%** (importe real negociado, los 2 lados + reequilibrio de lo mantenido) |
| Comisión total pagada | — (no se modela en dólares) | **1.161 $** (sobre 100.000 $ iniciales, ~9 años) |
| Sharpe estrategia (diario) | 0.71 | 0.70 |
| Sharpe SPY (diario) | 0.56 | **0.59** |
| **Gap de Sharpe vs SPY** | **0.151** | **0.111** |
| Max drawdown estrategia | −37.8% | −37.8% |
| Calmar | 0.48 | 0.48 |
| Días de recuperación (COVID) | 179 | 186 |

**Lectura honesta, con la misma disciplina de no sobreinterpretar que ya se aplicó al
resto de este documento**: la diferencia de Sharpe entre V1 y V2 (0.71 vs 0.70) es
minúscula frente al error estándar de ~0.37 (`sharpe_standard_error`) — no es que V2
"empeore" el resultado, es una medición más honesta del mismo resultado, prácticamente
igual en magnitud. Lo que sí cambia de forma real y explicable es **el margen frente al
SPY**: se reduce de 0.151 a 0.111 (~26% menos) porque las dos correcciones apuntan en
sentidos opuestos y ninguna favorecía antes a la estrategia — V1 penalizaba de más a la
propia estrategia con menos precisión de la que aparentaba (coste sobre el 100% de lo
mantenido) *y* penalizaba de más al SPY (rotación que nunca ocurriría en un índice
pasivo), y las dos cosas casi se cancelaban en el resultado agregado de V1. Con ambas
corregidas por separado, el resultado neto es un margen real pero **más modesto** que el
que sugería V1 — exactamente lo que el usuario anticipó ("probablemente cambiará bastante
tu sensibilidad a costes").

**Lo nuevo que V1 no podía mostrar**: capture ratio upside 108%/downside 95% — la
estrategia participa más de las subidas que de las bajadas del mercado, una asimetría
deseable y coherente con la tesis de calidad/momento, visible por primera vez porque
Calmar/capture/tracking error no existían antes de esta iteración. Beta 1.02 (exposición
de mercado casi neutra, como cabía esperar de una cesta de 20 large-caps del propio
S&P 500). Information Ratio 0.43.

**La auditoría completa posterior ya está disponible** en [docs/full-universe-audit](docs/full-universe-audit/README.md): valida desde enero de 2016 hasta octubre de 2025 sobre todos los constituyentes históricos disponibles, sin muestrear. El resultado reproducible es 23,68% CAGR neto para V2 Top-10 y 21,12% para V2 Top-20, frente a 15,00% de SPY. El resto de este apartado conserva la comparación anterior para no mezclar rangos ni motores. Sigue pendiente integrar V2 en la UI y mejorar las limitaciones de datos. La comparación anterior usa `max_symbols=200`; el sector point-in-time real vía
CIK/Entity Master en vez del sector actual; separar score y confidence en el scoring para
el missingness de métricas; separar explícitamente el modelo de selección del modelo de
cartera (Policy/optimizador de `decision_engine.py` usa reglas y pesos distintos a los de
la hipótesis congelada, y el optimizador min-vol recorta límites después de optimizar en
vez de dentro del problema). Tampoco se ha integrado V2 en la UI de Streamlit todavía.


### Paso 2: validación sobre el universo histórico completo (500 empresas, sin muestreo)

El usuario señaló una cuestión conceptual, no solo estadística: seleccionar las mejores 20
empresas de una muestra aleatoria de 200 no es la misma estrategia que seleccionar las
mejores 20 del S&P 500 completo — `max_symbols=200` es útil para iterar rápido, pero un
resultado que se vaya a citar como evidencia de la estrategia real debería usar el
universo completo, sin muestrear.

**`portfolio_backtest.run()` ahora exige `mode` explícito**, mutuamente excluyente con
`max_symbols`: `mode="validation"` (por defecto) exige `max_symbols=None` — universo
histórico completo, sin muestreo; `mode="fast_dev"` exige `max_symbols` (50/100/200) para
iterar rápido, y el resultado lleva `mode` marcado explícitamente para que un número de
`fast_dev` no se cite por error como validación real.

**Corrido de verdad, no solo implementado**: mismo rango (2016-07 a 2025-07, top-20,
trimestral), pero con el universo histórico completo cada trimestre (~460-500 empresas
elegibles según la fecha, frente a la muestra de 200 del paso 1) — 671 símbolos únicos
necesarios en todo el rango, 113 sin resolución de CIK (mismo hueco estructural ya
documentado), 36/36 periodos completos, sin ninguno saltado. Tardó ~26 minutos en total
(preparar datos + ejecutar), frente a los ~39s/periodo que tarda un `fast_dev` con datos
ya cacheados.

| | V2 `fast_dev` (muestra de 200, paso 1) | V2 `validation` (500 completo) |
|---|---|---|
| Retorno total estrategia | +347.3% | **+444.9%** |
| Turnover medio | 127.4% | **74.9%** (menor: con más candidatas elegibles, el ranking es más estable) |
| Comisión total pagada | 1.161 $ | 968 $ |
| Sharpe estrategia (diario) | 0.70 | **0.83** |
| Gap de Sharpe vs SPY (0.59 en ambos) | 0.111 | **0.243** |
| Max drawdown | −37.8% | −37.4% |
| Calmar | 0.48 | 0.56 |
| Information Ratio | 0.43 | 0.70 |
| Capture upside / downside | 108% / 95% | **111% / 86%** |

**Lectura honesta**: el universo completo rinde MEJOR en todos los frentes, no peor —
sorprendente si la hipótesis fuera "una muestra aleatoria más pequeña simplemente añade
ruido en ambas direcciones", pero coherente con un mecanismo concreto: con más candidatas
elegibles cada trimestre, el ranking tiene más profundidad para elegir y es más estable
(turnover baja de 127% a 75%), y la mejora de downside capture (95%→86%) sugiere que la
muestra de 200 estaba perdiendo algunas de las mejores opciones defensivas en las caídas.
Dicho esto, la diferencia de Sharpe (0.70 vs 0.83, gap 0.13) sigue siendo menor que un
error estándar completo (~0.39 con estos ~9 años de datos) — **no se declara una victoria
estadísticamente probada**, la misma disciplina que ya se aplicó al resto de este
documento. Lo que sí cambia con certeza es que **este número (`mode="validation"`) es
ahora el que debería citarse como evidencia de la estrategia real** — el de `fast_dev`
queda para iterar, no para reportar.

### Paso 3: sector point-in-time (entity_master.py) — corrige un look-ahead pequeño pero real

El usuario detectó un look-ahead conceptual, más sutil que usar beneficios futuros pero
real: `screener_asof.build_ranking_as_of` reconstruye fundamentales y precios point-in-time
correctamente (SEC EDGAR con `filed_date`, precios truncados a la fecha), pero para
sector/nombre usaba **el universo ACTUAL** (`universe.get_sp500_constituents()`, sin
fecha) — una empresa de 2016 se rankeaba dentro de su sector de **2026**, no del que tenía
entonces. Las empresas ya deslistadas se quedaban sin sector (caían al percentil global vía
el fallback ya existente en `scoring.py`), pero las que siguen cotizando hoy sí arrastraban
esta contaminación.

**No existe una fuente gratuita de sector histórico** — lo único honesto es empezar a
guardarlo desde ahora. Nuevo módulo **`src/gabi/entity_master.py`** (tests en
`tests/test_entity_master.py`, más un test dedicado en `test_screener_asof.py` que confirma
que `universe.get_sp500_constituents()` ya NO se llama en absoluto desde el ranking
histórico):

- `record_snapshot(universe_df, effective_date=None)`: guarda una foto con fecha de
  sector/industria/nombre — y el **CIK** resuelto vía `edgar.get_cik_for_symbol` (semilla
  de "Entity Master": identidad por CIK, no por ticker, que cambia/se recicla/desaparece —
  funcionalidad futura pedida explícitamente por el usuario; NO migra `prices`/
  `fundamentals`/`edgar_facts`, que siguen indexadas por símbolo — eso queda fuera de esta
  iteración). Enganchado a `screener.get_universe(force_refresh=True)`: cada vez que se
  confirma la composición del índice contra la fuente en vivo, se guarda una foto nueva.
- `get_sector_asof(symbols, as_of_date)`: la foto más reciente con `effective_date <=
  as_of_date` si existe (point-in-time real, `is_approximate=False`); si no, la foto más
  antigua disponible como aproximación explícita (`is_approximate=True`). Un símbolo sin
  ninguna foto (deslistado antes de que existiera esto) sigue devolviendo `sector=None`,
  igual que antes.

`build_ranking_as_of` ahora añade una columna `sector_is_approximate` a la tabla — visible
para cualquier código o UI que quiera distinguir sector point-in-time real de aproximado.

**Efecto en los resultados ya reportados en este documento: ninguno, verificado, no solo
asumido.** Antes de hoy no existía ninguna foto guardada, así que `get_sector_asof` cae
siempre a "sin foto más antigua disponible" — comportamiento idéntico al anterior (sector
actual) para CUALQUIER fecha histórica, con `is_approximate=True` en todas las filas. Los
206 tests existentes (incluidos los de V1/V2/`HIPOTESIS_CONGELADA.md`) pasan sin cambios.
**Declaración explícita, tal y como pidió el usuario**: todos los backtests de este
documento (V1, V2 paso 1 y paso 2) usan sector APROXIMADO (el actual, no el histórico real)
— dimensión conocida y ahora medible (`sector_is_approximate`), no oculta. A partir de hoy
(sembrada una foto real de las 503 empresas actuales, con CIK resuelto) GABI empieza a
acumular historial point-in-time real; dentro de meses/años, backtests que empiecen después
de hoy podrán usar sector genuinamente point-in-time para ese tramo.

### Paso 4: Score vs Confidence — cuánto fiarse de un score, no solo cuál es

El usuario señaló una sutileza real de `scoring.build_scores`: cada bloque (Value/Quality/
Momentum/Risk) promedia sus métricas ignorando las que faltan (`skipna=True`), y el
Composite renormaliza los pesos entre los bloques que sí existen. Consecuencia: una empresa
con **1 de las 4 métricas de Quality**, si esa única métrica está en percentil 95, obtiene
`quality_score = 95` — exactamente igual que otra con las 4 métricas en percentil 95. No
hay forma de distinguir, mirando solo el score, "score alto con mucho dato detrás" de
"score alto con casi ningún dato detrás".

**El modelo congelado no se toca** (petición explícita del usuario) — de las cuatro
alternativas que se plantearon (cobertura mínima por bloque, imputación al percentil 50,
penalización explícita, o separar score y confidence), se implementó la preferida por el
usuario: **`scoring.compute_confidence()`**, puramente aditiva, no cambia `build_scores` ni
ningún score existente (verificado con test dedicado — 211 tests en verde, sin cambios).

- **Score** sigue significando lo mismo: atractivo de la empresa.
- **Confidence** (nueva, 0-100, misma escala que los scores): cuánto fiarse de ese score.
  Por bloque, fracción de las métricas de `SCORE_METRICS[bloque]` con dato disponible (0 si
  el bloque entero falta, 1 si están todas); la confidence global es la media de las
  confidence por bloque, ponderada con los MISMOS pesos que el composite score — si el
  bloque con más peso es el que más falta, Confidence cae más que si es el de menos peso.

Ejemplo real (S&P 500, 2024-01-02): AAPL confidence=100 (13/13 métricas), MSFT=90, JPM=72.5,
XOM=31.7 (mucho dato ausente, coherente con que su `composite_score` también sale inválido
por baja cobertura). Cableado en ambos sitios donde se construye un ranking —
`screener.build_screener_table` (en vivo) y `screener_asof.build_ranking_as_of`
(point-in-time, usado por V1 y V2) — y visible en la UI (📊 Screener, tabla completa; 🔎
Ficha de Empresa, junto al resto de scores) para que un inversor junior vea de un vistazo si
un score alto merece confianza o se apoya en poco dato.

### Paso 5: señal vs cartera son dos estrategias distintas, y el optimizador ya no recorta después de resolver

El usuario señaló dos problemas reales en `decision_engine.py` (🧭 Decisiones de cartera):

**1. Se presentaba como si fuera una consecuencia de la hipótesis congelada, y no lo es.**
`HIPOTESIS_CONGELADA.md` valida: 20 posiciones equiponderadas, pesos 30/35/25/10, rebalanceo
trimestral, sin filtro de tendencia. `Policy` por defecto usa: máximo 10 posiciones, filtro
duro de precio sobre SMA200 (ni siquiera configurable — hardcodeado en `_reasons()`), y
reparto por **mínima volatilidad** (PyPortfolioOpt), no equiponderado. Es una estrategia
legítima, pero nunca se ha contrastado con un backtest — y la UI no lo decía en ningún
sitio. **Arreglado con un aviso explícito** en 🧭 Decisiones de cartera: dice exactamente
qué distingue a esta estrategia de la validada, para no dar a entender que hereda la
validación del backtest.

**2. El optimizador no resolvía el problema que decía resolver.** `_risk_weights` calculaba
la cartera de mínima volatilidad **sin ningún límite** (`weight_bounds=(0, 1)`, sin límite de
posición ni de sector pasado al solver) y **después** `build_plan` recortaba con un bucle de
un solo paso (`min(peso, max_position_pct, hueco_de_sector)`, sin redistribuir lo recortado).
Consecuencia: tras el recorte, la cartera **ya no es la de mínima volatilidad** — es una
aproximación recortada y subóptima, con peso sobrante que simplemente queda sin invertir en
vez de repartirse entre el resto de candidatas.

**Arreglado, opt-in (`Policy.constrained_optimizer=True`, por defecto `False` — no cambia el
comportamiento existente ni los tests que ya dependían de él)**: nueva
`_risk_weights_constrained()` pasa los límites de posición y sector **dentro del propio
problema** de optimización, usando capacidades nativas de PyPortfolioOpt en vez de recortar
después:
- `weight_bounds=(0, max_position_pct/presupuesto_invertible)` — límite de posición real,
  no una caja sin restricciones seguida de un clip.
- `ef.add_sector_constraints(...)` — límite de sector dentro del solver.
- `ef.add_objective(objective_functions.transaction_cost, w_prev=..., k=turnover_penalty)`
  — **penalización por turnover** pedida explícitamente por el usuario: penaliza alejarse de
  las posiciones actuales en el propio objetivo, para no rotar la cartera solo por ruido de
  recalcular con datos ligeramente distintos.
- Si los límites son demasiado estrechos para poder invertir el 100% del presupuesto con las
  candidatas disponibles (`max_positions × max_position_pct < max_invested_pct` — un caso
  real, no hipotético: ocurre con los valores por defecto si sobreviven menos de 10
  candidatas), el problema restringido es infactible — cae automáticamente al comportamiento
  de siempre (sin límites + recorte posterior) en vez de fallar.

Verificado con tests dedicados (límites respetados exactamente con el solver real, caída
elegante en el caso infactible, y que la penalización por turnover de verdad acerca los pesos
a la cartera actual frente a no penalizar) — 215 tests en total, ninguno de los 10 tests
previos de `decision_engine.py` cambia de comportamiento. Disponible desde la UI (🧭
Decisiones de cartera → "Reglas y límites" → casilla "Portfolio Engine V2").

## 🔬 Research Lab: registro de experimentos + rigor estadístico

Propuesta del usuario, motivada por algo que esta misma sesión ya hacía a mano: se probaron 10+
configuraciones sobre el mismo rango 2016-2025 (top-10/20/30, filtro SMA200, banda de turnover,
3 frecuencias de rebalanceo, universo 200 vs 500, V1 vs V2), documentando cada vez si el resultado
era ruido o señal. El Research Lab formaliza esa disciplina: un registro de experimentos
(`src/gabi/research_lab.py`, tabla `experiments`, página 🔬 Research Lab) con metodología, commit
de código exacto y resultado, etiquetado por fase (**RESEARCH** / **IN_SAMPLE** / **OUT_OF_SAMPLE**
/ **LIVE_FORWARD**), y un módulo de rigor estadístico (`src/gabi/stats_rigor.py`) que implementa
Probabilistic Sharpe Ratio → Deflated Sharpe Ratio → PBO/CSCV → intervalos de confianza bootstrap
(Bailey & López de Prado; umbral t>3 de Harvey, Liu & Zhu ya citado en `HIPOTESIS_CONGELADA.md`).

**Límite real, comunicado con la misma honestidad que el resto de este documento**: los ~10
experimentos ya documentados en este README solo tienen métricas RESUMEN (Sharpe, Sortino,
drawdown) — no se guardó la serie de retornos completa de cada uno en su momento. Sembrar el
registro con ellos permite un **DSR real** (solo necesita el Sharpe de cada intento y cuántos se
probaron), pero el **PSR exacto, PBO y bootstrap necesitan la serie de retornos real**, que no
existe para esos experimentos históricos — se usa una aproximación normal (skew=0, kurtosis=3,
equivalente a `sharpe_standard_error`) para ellos, marcada explícitamente como aproximación.
Cualquier experimento registrado desde 🕰️ Ranking histórico a partir de ahora SÍ guarda la serie de
retornos real (V1: retorno por periodo; V2: retorno diario de la curva NAV), así que PSR
exacto/PBO/bootstrap están disponibles de verdad para lo que se registre de aquí en adelante.

**Sembrado con 9 experimentos reales** (familias `posiciones_frecuencia_v1` — top-10/20/30, +filtro
SMA200, semestral/anual, banda 1.5x, todos con el muestreo y el drawdown-por-snapshot ya
corregidos — y `universo_v2` — V2 fast_dev vs validation), cada uno con su cita exacta a la sección
del README de la que sale. **Resultado real del primer cálculo de DSR sobre la hipótesis
congelada** (Top-20 trimestral, N=7 intentos de la familia `posiciones_frecuencia_v1`):

| | Valor |
|---|---|
| PSR sin deflactar (vs Sharpe=0) | 97.9% |
| SR*₀ (máximo esperado por azar, N=7) | 0.11 |
| **DSR (deflactado por los 7 intentos)** | **95.8%** |

Con solo 7 configuraciones probadas y 36 observaciones trimestrales, la corrección por *multiple
testing* apenas mueve la aguja (97.9%→95.8%) — un resultado tranquilizador, pero que no habría sido
así con más intentos o menos historia: el propio cálculo de `expected_max_sharpe` muestra que SR*₀
crece con N, así que esta cifra debe repetirse si en el futuro se añaden más configuraciones a la
familia.

**Cómo se usa**: desde 🕰️ Ranking histórico, tras ejecutar un backtest (V1 o V2), un botón "📋
Registrar este experimento en el Research Lab" pre-rellena la metodología y el resultado — la fase
(RESEARCH/IN_SAMPLE/OUT_OF_SAMPLE/LIVE_FORWARD) es una decisión del usuario sobre su propia
intención con ese run, no algo que el código pueda inferir. Desde 🔬 Research Lab: tabla de
experimentos filtrable por familia/fase, formulario de registro manual, y las tres secciones de
cálculo (PSR/DSR, PBO/CSCV, bootstrap) — estas dos últimas solo ofrecen experimentos con serie de
retornos guardada.

## 📐 Factor Lab: ¿el score predice de forma gradual y consistente?

Segunda propuesta del usuario tras el Research Lab. En vez de seguir preguntando "¿el Top-20 ganó al
SPY?" (una pregunta binaria sobre una cesta concreta), una más informativa: **¿el Composite Score —y
cada uno de sus bloques— contiene información predictiva de forma gradual y consistente?** Cada
rebalanceo, el universo se divide en quintiles por score (Q1 peor → Q5 mejor) y se mide el retorno
FUTURO real a 1/3/6/12 meses de cada quintil — si el score funciona, se espera una relación
razonablemente monotónica (no necesariamente perfecta ni todos los periodos), no solo que una cesta
concreta ganara al índice.

**`src/gabi/factor_lab.py`** (página 📐 Factor Lab) reutiliza tal cual la reconstrucción point-in-time
ya existente (`universe.get_sp500_constituents_asof` + `screener_asof.build_ranking_as_of`, mismo
contrato `mode="validation"`/`"fast_dev"` de `portfolio_backtest.py`) y el mismo patrón de sesión de
entrada de `multifactor_backtest._period_returns` — el retorno futuro que mide **nunca lleva coste**
(esto mide información del score, no el resultado de una cartera con fricción). Por cada (fecha,
factor, horizonte) calcula:

- **Rank IC** (Spearman) entre score y retorno futuro real.
- **ICIR** (IC medio / desviación típica del IC en el tiempo) — mide si el IC es consistente, no solo
  alto de media.
- **% de periodos con IC>0**, spread **Q_máx−Q1**, y **turnover por quintil** (se asigna una vez por
  fecha+factor con el score de esa fecha, independiente del horizonte).
- **Versión sector-neutral** (en la misma pasada, no una ejecución aparte): retorno de cada empresa
  menos la media de su sector ese periodo, antes de calcular IC/quintiles — aísla si el score elige
  ganadores DENTRO de su sector o solo capta qué sector estuvo de moda. Corregido durante el desarrollo
  un fallo real: un solo símbolo sin sector asignado (ver `entity_master.py`, Paso 3) descartaba el IC
  sector-neutral del periodo ENTERO en vez de solo esa fila — ahora se excluyen únicamente las filas sin
  sector, comprobado con datos reales (una prueba pequeña pasó de 0 filas sector-neutral calculables a
  las 15 esperadas tras el arreglo).

Verificado con casos de referencia sintéticos, no solo "no rompe" (`tests/test_factor_lab.py`): un score
que ordena perfectamente el retorno futuro da IC≈1 y spread claramente positivo; un score sin relación
da IC≈0; turnover exactamente 0% con quintiles idénticos y 100% cuando cambian por completo; y el caso
clave del sector-neutral — un score correlacionado solo con el sector (sin ninguna relación específica
de empresa) da un IC crudo artificialmente alto que el sector-neutral filtra correctamente a ~0.

Puede descubrirse que un bloque entero (ej. Risk) no aporta prácticamente nada en ningún horizonte — esa
es información tan valiosa como encontrar uno que sí funcione, y mucho más que seguir ajustando pesos
para maximizar el CAGR de una cesta concreta.

## 🔒 Blind Forward Validation

Tercera propuesta del usuario. `HIPOTESIS_CONGELADA.md` prometía una validación prospectiva real (4
rebalanceos trimestrales reales, 2026-Q4 a 2027-Q3, sin tocar la estrategia hasta 2027-09-17) — promesa
que se rompió el mismo día que se escribió ("Descongelemos la hipótesis"), una decisión legítima y
documentada, pero que deja sin resolver el problema real: **nada en el código impedía mirar el
resultado a medias y "ajustar un poco" la estrategia**, la tentación exacta que describe el usuario
("llevamos seis meses perdiendo, quizá Momentum debería pasar de 25 a 35%..." — en cuanto se hace eso,
la prueba prospectiva ha muerto, sin que nadie necesite hacer trampa conscientemente).

**`src/gabi/blind_validation.py`** (página 🔒 Blind Forward Validation) convierte esa promesa en algo
real: cada rebalanceo se registra de forma **inmutable** (`UNIQUE(validation_id, rebalance_date)` —
reintentar el mismo periodo lanza, no sobrescribe) con picks, precios de entrada reales, commit de
código (`git rev-parse --short HEAD`, reutilizado de `research_lab.py`), y un **hash encadenado con el
anterior** (`record_hash = sha256(prev_hash + datos_del_periodo)`) — si alguien edita un periodo antiguo
a mano en la base de datos, `verify_integrity()` lo detecta porque la cadena deja de encajar (probado
con una manipulación real en el test). Mientras la validación está bloqueada, **`get_status()` no
incluye ninguna clave de rendimiento en el diccionario que devuelve** (no solo las oculta en la UI —
comprobado explícitamente con un test que el dict ni siquiera contiene `"performance"`), así que no hay
ningún camino por el que un resultado a medias se pueda colar en pantalla por accidente.

**Honestidad en vez de un candado falso**: una app local no puede impedir de verdad que su propio dueño
mire su base de datos a mano. `break_seal_early(reason)` no finge ser irrompible — permite romper el
sello antes de tiempo si el usuario decide hacerlo conscientemente, pero deja constancia PERMANENTE de
que se rompió y por qué, igual que se documentó la propia ruptura de `HIPOTESIS_CONGELADA.md` esta
sesión. Una vez desbloqueada (por fecha o por ruptura consciente), `export_to_research_lab()` registra
el resultado real como experimento `LIVE_FORWARD` en 🔬 Research Lab — conecta directamente con el
registro ya existente en vez de duplicarlo.

Verificado con datos reales, no solo con mocks: creada una validación de prueba, registrado un
rebalanceo real (10 símbolos reales del ranking de hoy, precios reales), confirmado que `get_status()`
bloqueado no expone ninguna clave de rendimiento y que la integridad verifica correctamente — y limpiado
después de la prueba.

## 🧮 Portfolio Lab: comparar esquemas de ponderación + stress tests

Cuarta propuesta del usuario, la más grande de las cuatro. Hasta ahora todo el backtesting asumía
implícitamente que repartir el capital a partes iguales entre las candidatas del ranking ("Equal Weight")
era "la" forma de construir la cartera. **`src/gabi/portfolio_lab.py`** (página 🧮 Portfolio Lab) compara,
sin declarar ganador de antemano, seis esquemas sobre las MISMAS candidatas de cada rebalanceo: **Equal
Weight, Inverse Volatility, Minimum Variance, Score-weighted, Score + risk constrained y Risk Parity** —
con rentabilidad, volatilidad, drawdown, turnover, coste, concentración (HHI), contribution-to-risk y
tracking error frente al SPY para cada uno, más una serie de stress tests explícitamente marcados como
**no pronósticos**.

**Reutilización, no reinvención**: Minimum Variance reutiliza directamente `decision_engine._risk_weights`
(sin límites); Score + risk constrained sigue el mismo patrón que `decision_engine._risk_weights_constrained`
(límites de posición/sector dentro del propio solver de PyPortfolioOpt, con `max_quadratic_utility()` en vez
de `min_volatility()`); la ejecución real de cartera reutiliza `_apply_trade`/`_daily_segment`/
`buy_and_hold_curve` de `portfolio_backtest.py` sin cambios. Lo único genuinamente nuevo es CÓMO se calcula
el peso objetivo de cada esquema — para eso, `portfolio_backtest._rebalance` (antes solo equiponderado) se
generalizó a `_rebalance_to_weights(target_weights)`, con `_rebalance` como caso particular
`{s: 1/top_n}` — refactor verificado puro: los 17 tests ya existentes de `test_portfolio_backtest.py`
siguen pasando exactamente igual tras el cambio.

**Insight de rendimiento**: reconstruir el ranking point-in-time es el paso caro del bucle y es el MISMO
para los 6 esquemas en una fecha dada — se hace una sola vez por periodo, y los 6 esquemas se calculan
sobre esas mismas candidatas (optimizar sobre 20-50 valores es cuestión de milisegundos), así que el coste
total es aproximadamente el de un solo backtest V2, no seis.

**Tres bugs reales encontrados y corregidos durante el desarrollo** (con una prueba de integración real
antes de escribir los tests unitarios, no solo revisando el código):

1. **Look-ahead en el cálculo de pesos** (el más importante): `.tail(252)` sobre el historial de precios
   en caché tomaba los últimos 252 días HASTA HOY, no los 252 anteriores a la fecha de cada rebalanceo —
   comprobado con datos reales: un backtest de 2019 estaba construyendo la covarianza con precios de
   2025-2026. Corregido truncando `histories` a `<= entry_session` inmediatamente después de obtenerlas,
   el mismo patrón que ya usa `decision_engine.build_plan`. Hay un test de regresión específico
   (`test_run_portfolio_lab_point_in_time_ignores_future_price_spike`) que inyecta un pico de volatilidad
   FUTURO y comprueba que no afecta a los pesos calculados en un rebalanceo anterior.
2. **`pypfopt.hierarchical_portfolio.HRPOpt` roto en este entorno** (`AttributeError: module
   'scipy.cluster.hierarchy' has no attribute '_LINKAGE_METHODS'`, confirmado de forma aislada). Risk
   Parity se resuelve en su lugar a mano: minimizar con `scipy.optimize.minimize` (SLSQP) la dispersión
   entre la `contribution_to_risk` de cada posición y `1/N` — Equal Risk Contribution, el mismo objetivo
   que persigue HRP, sin depender de esa clase.
3. **Faltaba "SPY" en los símbolos descargados para cada periodo**, así que `compute_betas` siempre
   recibía un historial vacío para el SPY y todas las betas caían silenciosamente a 1.0 — se notó porque
   el impacto de "S&P −10%" salía idéntico en los 6 esquemas, algo estadísticamente inverosímil. Corregido
   añadiendo `SPY` al conjunto de símbolos necesarios cada periodo.

Verificado con una ejecución real pequeña (`mode="fast_dev"`, 2019-01 a 2019-10, 25 símbolos, top-8) tras
las tres correcciones: los impactos de "S&P −10%" pasaron a diferir genuinamente por esquema
(−7.0% a −8.3% según cuánto beta lleve cada cartera) y Risk Parity dejó de coincidir con Equal Weight
(Sharpe, HHI y top-3 contribution-to-risk todos distintos). Un caso adicional observado y verificado como
comportamiento esperado, no un bug: en ese mismo test, Score-weighted y Score + risk constrained daban
HHI/turnover/escenarios idénticos en el último periodo (aunque el Sharpe total difería) — investigado
directamente reproduciendo el solver sin capturar la excepción: el segundo periodo lanzaba
`OptimizationError: infeasible` (los límites de 20% posición / 35% sector son incompatibles con esas 8
candidatas concretas), así que ese periodo cae al fallback documentado (`_weights_score`) — el primer
periodo sí había convergido con pesos genuinamente distintos (capados a 20%, dos posiciones a 0%), lo que
explica que el Sharpe total difiriera aunque los pesos del ÚLTIMO rebalanceo coincidieran.

**Stress tests, separados explícitamente en dos grupos de confianza** (`SCENARIO_GROUND`, marcado también
en la UI con 🟢/⚠️): S&P −10%/−20%, Tecnología −25% y Volatilidad ×2 usan beta/sector calculados de
precios reales cacheados; Tipos +100pb y USD ±10% usan una tabla de sensibilidad por sector **sin
calibrar** (GABI no tiene datos de duración ni de exposición a divisa por empresa) — se presentan como
orientativos, nunca con la misma solidez aparente que los primeros cuatro. Ninguno pretende ser un
pronóstico: son shocks arbitrarios aplicados con supuestos simples y explícitos sobre los pesos del último
rebalanceo, pensados para responder a preguntas como "esta cartera tiene 20 empresas, pero 3 de ellas
representan un 34% del riesgo" — información mucho más útil para un junior que "20 posiciones =
diversificada".

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

## Validación de datos anteriores a 2016

Se han importado los 28 paquetes SEC de 2009–2015 y recuperado contextos
originales para contrastar 454.341 registros. Un extractor con especificaciones
revisadas cubre un piloto de Microsoft 1996, Lehman 2007 y Apple 2008. El informe
de 80 trimestres distingue métricas calculables de identidad y sector históricos
acreditados; todavía no certifica un backtest completo desde 1996.

Los resultados, fuentes, límites y comandos están en
[la validación histórica 1996–2015](docs/historical-validation-1996-2015/README.md).
La cobertura también se muestra en **Calidad de los datos → Archivo histórico
anterior a 2016**.

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
