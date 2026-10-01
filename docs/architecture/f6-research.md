# F6 · Investigación y distribución local (#68)

F6 se entrega por recorridos verificables. Este primer tramo sustituye la portada
vacía de Investigación por el catálogo **ya publicado** en
`docs/search-ledger/ledger.json`: 34 entradas de la convención histórica,
observaciones adicionales, diagnósticos, fallos y límites. No calcula ni abre
ninguna reserva; el registro publicado declara expresamente que su recuento no es
exhaustivo ni controla el error global de todas las búsquedas. La #60 permanece
pendiente de evidencia independiente.

La API lee solo el fichero explícito, con tope de 2 MB, y almacena su JSON en
memoria hasta que cambian tamaño o mtime. La CI verifica el registro frente a
sus fuentes publicadas. Las respuestas seleccionan campos de metadatos;
`configuration` y cualquier campo adicional quedan fuera del contrato. No se
consulta `gabi.db`, resultados operativos, periodos ciegos ni los datasets
reservados de #43/#44. Una ausencia o estructura inesperada devuelve 503.

El Ranking histórico reconstruye por job una fecha del S&P 500 en el intervalo
ya observado 2010-01-01 a 2025-07-02. La validación de fechas está en el
backend: ni la UI ni una llamada directa pueden abrir el periodo pre-2010 de
#43 o fechas prospectivas. El worker usa el motor legacy intacto y conserva
todas las filas en un artefacto JSON con hash; la pantalla presenta las primeras
100 y permite descargar el resultado completo. Es exploración retrospectiva,
no validación fuera de muestra.
Los backtests V1 (coste plano por lado) y V2 (acciones y caja, comisión fija y
spread, curva diaria) se ejecutan ahora con los jobs `backtest_v1` y
`backtest_v2`, solo en modo Research y con los mismos parámetros que Streamlit:
rebalanceo, empresas, umbral de rotación, coste/universo en V1 y modo, muestra,
capital, comisión y spread en V2. El caso de uso rechaza claves ajenas al motor,
muestras incoherentes con el modo y cualquier ventana fuera de 2010-01-01 a
2025-07-02; la sesión de salida del último periodo no supera ese corte. La
comprobación se repite al leer artefactos persistidos. El adaptador legacy llama a
`multifactor_backtest.run` y `portfolio_backtest.run` sin cambiarlos y calcula las
métricas de V2 (diarias, Calmar, recuperación, beta, Information Ratio y
capturas) con las mismas funciones que la página antigua; una prueba compara
ambos resultados. El artefacto conserva parámetros normalizados, periodos,
saltados, calidad de datos, salidas por baja y la curva (hasta 200 periodos y
5.000 puntos) con SHA-256; React presenta métricas, curva y tablas y permite
descargarlo íntegro. El job no descarga datos: la preparación sigue siendo una
acción aparte. Los motores leen el historial de precios como antes; no se ha
medido ni acotado esa lectura en este cambio.
El registro en Research Lab es otro job explícito, `backtest_register`, en modo
Research. Recibe el backtest de origen, la fase, la familia, si la hipótesis se
registró antes y las notas; relee el artefacto verificando su SHA-256, repite la
comprobación del periodo observado y traduce el resultado a los mismos campos que
Streamlit pasaba a `research_lab.log_experiment` (una prueba los compara,
incluida la serie de retornos). El experimento añade a `result_json` el job de
origen, su hash y `data_fingerprint_scope="registration"`: la huella
`compute_data_fingerprint()` completa se calcula al registrar, no al terminar el
backtest como hacía Streamlit, porque recorre todas las tablas de la base. En la
base local de 12 GB tardó 1.937 s con 7,2 MiB de pico Python (`tracemalloc`),
medido mientras otra verificación leía la misma base; no se atribuye esa cifra a
una ejecución aislada. Un backtest solo puede registrarse una vez; un segundo intento falla
sin escribir.
El riesgo de cola (V1 por rebalanceo si todos los periodos duran lo mismo; V2 por
sesión sobre la NAV diaria) y el drag fiscal español de V1 se consultan con
`GET /research/backtests/{id}/diagnostics`. La consulta relee el artefacto
verificado y aplica `portfolio_metrics.tail_risk_metrics` y
`tax_drag.simulate_tax_drag` mediante un adaptador legacy inyectado en el
bootstrap; no descarga, no escribe y no ejecuta el backtest. El capital de la
simulación fiscal se limita a 1.000-100.000.000 €. Las pruebas comparan ambos
resultados con las llamadas de la página antigua.
El contraste Fama-French 5 + Momentum es el job explícito `backtest_factors`,
solo para V1 como en Streamlit, con retardos HAC automáticos o fijados antes de
ver el resultado. Usa `data/ff_factors.csv` y solo descarga los factores de
Kenneth French si esa copia no existe. Ejecuta la regresión HAC, la estabilidad
temporal y el benchmark ajustado por beta y factores con los módulos sin cambios;
un fallo en una parte conserva su mensaje sin ocultar las demás. El artefacto
guarda el backtest de origen y su hash, y el SHA-256 y los meses del fichero de
factores; al leerlo se repite la comprobación del periodo del backtest de origen.
React presenta el alfa, las betas, la estabilidad por mitades, las ventanas
móviles con su intervalo, los episodios y las curvas del benchmark. Las tablas de
regresiones in-sample y de coeficientes por entrenamiento expansivo solo están en
el JSON descargable.
Los dos botones "Preparar datos" son el job explícito `prepare_history`, sin
modo Research porque no lee resultados. Por fecha, prepara 15, 50 o todas las
empresas del universo de esa fecha con `edgar.ensure_edgar_data(..., as_of)` y
`data_fetch.ensure_price_history_asof`; para un backtest, los símbolos de
`multifactor_backtest.required_symbols` con SEC EDGAR y precios `max` en lotes de
25 más SPY, igual que la página antigua. Es la única acción de estas pantallas
que usa la red y escribe en la base; las fechas se limitan al periodo observado
y el resultado lista hasta 1.000 fallos por símbolo y etapa.
La vista del ranking histórico calcula ahora en el backend la misma cobertura que
Streamlit sobre todas las filas del artefacto, no solo las 100 mostradas: capa
histórica 2010-2015 y sus exclusiones, identidades ambiguas o sin acreditar,
recuentos de fundamentales, precio y sector, y los avisos de sector y de bloques
del score con `data_quality.score_block_coverage`/`block_coverage_warnings` y el
umbral de cobertura (70 % por defecto, como el control lateral antiguo). Los
diagnósticos de V1/V2 añaden los avisos por rebalanceo de
`ranking_quality_warnings` sobre la calidad guardada en el artefacto. Las
pruebas comparan los textos con las expresiones de la página antigua.
La tabla de métricas reconstruidas se consulta paginada (100 filas, máximo 200)
con `GET /research/historical/{id}/table`: las mismas columnas y etiquetas de la
página antigua, "ocultar empresas sin ningún dato" y orden por una columna en el
backend. El color de cada celda es el percentil sectorial `<métrica>_pct` que ya
calculó el motor, o el propio score, igual que `build_color_basis`; React solo lo
pinta con la misma escala. Cada columna declara su unidad: `shares_dilution_yoy`,
`buyback_yield` y `capex_to_ocf` son fracciones y `acquisitions_latest` dólares,
aunque la tabla antigua los imprimía sin convertir. El job del ranking guarda
ahora el nombre SEC resuelto de cada símbolo, que Streamlit consultaba en cada
render; los artefactos anteriores usan el nombre del motor.
El resultado posterior de las primeras candidatas (6 y 12 meses) y la
comparación por bloques (12 meses) son el job `historical_outcomes`, en modo
Research, sobre un ranking ya calculado: misma selección que la página antigua
(primeras N con Composite; N líderes de cada bloque con cobertura >= 50 %) y la
fórmula sin cambios de `evaluation.evaluate`. `evaluate` acepta ahora un lector de
precios y un corte opcionales, con el comportamiento anterior por defecto. El job
inyecta `SqliteWindowPrices`, que lee en solo lectura la ventana de ±7 días de
cada fecha (la misma tolerancia de `_adjusted_at`) y rechaza cualquier ventana
posterior al 2025-07-02. Si fecha + horizonte + 7 días supera ese corte, el
horizonte se marca como reservado sin consultar sus precios; Streamlit lo
calculaba o lo dejaba como pendiente según la fecha de hoy. Una prueba compara
el lector acotado con `_adjusted_at` y el resultado con la llamada antigua. Con
esto la página de Ranking histórico queda cubierta en React; el tamaño de
universo 15/50 de la reconstrucción antigua era solo una muestra más rápida del
universo completo que calcula el job.
El job exploratorio `backtest` que ya existía en Administración también queda
limitado a la misma ventana observada. La API verifica la fecha tanto al
encolar como al leer artefactos de jobs antiguos: una URL directa no puede
eludir la reserva de #43. El universo del motor sigue siendo S&P 500; no se
ofrece el conjunto reservado fuera del índice de #44.
La consulta `blind-validations` lee solo metadatos y registros de sellos desde
SQLite en modo de solo lectura. Verifica la cadena con la misma función pura
que usa el módulo Streamlit, con topes de 50 validaciones, 100 periodos por
validación, 1.000 periodos totales y 16.384 caracteres por campo JSON;
excederlos devuelve 503 sin recortar silenciosamente. Nunca devuelve
símbolos, precios de entrada, pesos ni rendimiento, incluso tras el desbloqueo.
Cada consulta relee los registros, por lo que no existe una caché de sellos que
pueda quedar obsoleta. El alta, los rebalanceos y la revelación aún no se han
migrado.

Factor Lab se ejecuta ahora por `factor_analysis` en el worker, con el motor
histórico y sus cinco scores, cuatro horizontes y quintiles originales sin
cambiar sus fórmulas. El comando fija rebalanceo (1/3/6/12 meses), modo
`validation` con universo completo o `fast_dev` con 50/100/200 empresas. El
servidor exige el modo Research local tanto para encolar como para leer el
resultado. Administración en React permite cambiar Investor/Research mediante
un comando explícito que guarda `data/app_mode.json` de forma atómica, compatible
con Streamlit. Las consultas leen el modo sin escribir ni descargar datos; un
cambio invalida las consultas activas del cliente. Volver a Investor bloquea
los trabajos de investigación y usa los pesos congelados sin borrar los pesos
Research guardados.
Solo admite ventanas desde 2010 de hasta seis años y un fin máximo de
2024-07-01: el horizonte de
12 meses no puede alcanzar los datos prospectivos posteriores al corte observado
de 2025-07-02. La comprobación se repite al leer el artefacto, también para jobs
persistidos. El resultado íntegro (series IC, quintiles, rotación, periodos
saltados) se guarda con SHA-256 y límite de 10 MB; React presenta el resumen
tipado y permite descargar el JSON. Cada ejecución es un ensayo retrospectivo;
`fast_dev` es muestreo y ningún resultado se promociona automáticamente a
evidencia independiente. El job no usa caché de cálculo: se ejecuta solo por
acción explícita y el artefacto queda invalidado únicamente si se cancela,
falla o su hash ya no coincide. El estado de capturas de estimaciones se consulta
ahora también en React. SQLite se abre en modo de solo lectura y una agregación
devuelve solo recuentos y primeras/últimas fechas de lotes con al menos 20
símbolos; no carga filas de símbolos ni inicializa el esquema. Se muestran los
umbrales heredados de 6 capturas y 60 días, pero la consulta nunca calcula IC
o retornos y no afirma ventaja independiente. La evaluación se inicia ahora solo
con el job `estimate_analysis` en modo Research. Reutiliza el cálculo Rank IC
heredado con lectores inyectados de solo lectura: como máximo 64 capturas de
1.000 símbolos y 300.000 filas de precios por ventana, entre 2010-01-01 y el
corte observado 2025-07-02. Los horizontes son 1 y 3 meses; las sesiones de
salida posteriores al corte se omiten antes de leer precios. El artefacto
íntegro se publica con hash y el backend vuelve a comprobar su corte antes de
entregarlo. No hay caché de cálculo: repetir el experimento requiere otro job.
Una captura con hora se normaliza al día para el calendario bursátil, conservando
su `captured_at` real. La comparación con la fórmula heredada y la ausencia de
escrituras del nuevo lector se prueban con datos temporales. Streamlit ya no
ejecuta esa evaluación automáticamente al renderizar; remite al job de React.
El resumen del job incluye además el retorno medio por quintil de cada factor y
horizonte, bruto y sector-neutral, y la lista de periodos saltados con su motivo.
El backend agrega las filas `quantile_returns` del artefacto con la misma media
por quintil que el gráfico de Streamlit (una prueba compara ambos valores
exactos); React solo elige factor/horizonte y formatea porcentajes. El decay del
IC se lee en la tabla por horizonte y la rotación se muestra por quintil en vez
de su media por factor; los valores de origen son los mismos del artefacto.
El mapa Factor Zoo publicado y el diagnóstico SIC fechado se consultan ahora
también en React. La API verifica los preregistros, el manifiesto, los siete
resultados publicados, el código congelado del suplemento y sus cinco CSV antes
de exponer solo el resumen, la cobertura y tres exportaciones permitidas. La
primera lectura tiene un límite agregado de 16 MB; las siguientes comparan
identidad, tamaño y tiempos de modificación/cambio de los archivos, y repiten
las huellas si alguno cambia. Streamlit presenta el mismo caso de uso mediante
su verificador heredado, también con invalidación por metadatos entre renders.
Las cachés no incluyen `data/`, SQLite, fuentes externas ni resultados reservados. Un cambio
o ausencia invalida el resultado y devuelve 503. Los diagnósticos SIC siguen
siendo descriptivos, sin cambio de p-valores, pesos ni confianza de evidencia.
Medición de lectura local de los artefactos ya publicados, Windows/Python 3.13.7:
`evidence_catalog.load()` heredado 0,0549 s, primera verificación nueva 0,0551 s,
y consulta cacheada 0,000905 s de mediana en 20 repeticiones. La primera lectura
no mejora materialmente; los tiempos no incluyen render de React ni `data/`.
El worker inyecta un lector SQLite de solo lectura limitado a las sesiones de
entrada/salida de cada periodo, 1.000 símbolos y 300.000 filas por consulta;
la función antigua conserva su entrada previa para Streamlit. Una prueba con
datos temporales compara todos los DataFrames resultantes. Medición de una
lectura, no del análisis completo: `python scripts/measure_f6_factor_prices.py`,
Windows/Python 3.12, 50 símbolos y 2.348 sesiones sintéticas: la lectura de
historial completo tardó 0,808 s y tuvo 39,665 MiB de pico Python; la ventana
de 260 sesiones tardó 0,176 s y tuvo 3,360 MiB. No se extrapolan esas cifras
a la base local de 83 GB.
Medición de la serialización, no del cálculo histórico ni de SQLite:
`python scripts/measure_f6_historical.py` en Windows/Python 3.13.7, fixture
sintética de 500 empresas y 62 columnas, 999.398 bytes JSON, 0,3844 s y
3,454 MiB de pico de asignaciones Python medido con `tracemalloc`. El resultado
queda bajo el límite de 10 MB del worker en esta fixture; no se extrapola a
los datos locales ni se atribuye una mejora de rendimiento al cambio de UI.

El build de Vite puede servirse desde FastAPI bajo `127.0.0.1:8000`; el mismo
origen sirve `/api/v1`, `/assets` y las rutas de React. `gabi_cli serve` inicia
API y worker, los detiene juntos y exige un build presente. El modo de desarrollo
con Vite continúa disponible. No se retira Streamlit mientras falten sustitutos
de los recorridos de Investigación y la pestaña de backtest SMA heredada.

La página Streamlit `8_Ranking_Historico.py` se ha retirado tras comprobar la
equivalencia con la base local. El 2012-06-01 (497 empresas, capa histórica),
el camino antiguo y los jobs nuevos coincidieron sin diferencias en orden del
ranking, avisos y recuentos de cobertura, valores y colores de cada celda,
candidatas, resultado a 6 y 12 meses y los cuatro bloques (184 s frente a 181 s;
`gabi.db` sin cambios y red bloqueada). Los backtests V1 (500 empresas) y V2
(muestra de 200) de 2012 coincidieron en métricas, costes, curva y periodos;
las únicas discrepancias fueron el redondeo a 10 decimales del script de
comparación. No se comprobó V2 con el universo completo ni fechas 2016-2025,
porque la base local todavía no resuelve esas identidades. Se retiran su
entrada de navegación y su excepción de arquitectura; los módulos que usaba
siguen en uso por otras páginas o por los adaptadores legacy nuevos, y la
historia publicada no se modifica.

La página Streamlit `12_Factor_Lab.py` y su adaptador `factor_sector_ui.py`
también se han retirado tras comprobar la equivalencia con la base local. El
mapa Factor Zoo/SIC del verificador antiguo y el lector de React coincidieron en
las 13 señales. `factor_lab.run_factor_analysis` directo (historial completo) y el
job con el lector acotado coincidieron exactamente en resumen, series IC,
quintiles, rotación, periodos saltados y medias por quintil, en `fast_dev` con 100
empresas (2011-07 a 2013-07, 259 s frente a 261 s) y en `validation` con el
universo completo (primer semestre de 2012, 346 s frente a 332 s), con `gabi.db`
sin cambios y red bloqueada. La prueba de la API sigue comparando el mapa con las
fuentes selladas (`evidence_catalog` y `factor_sector_stability.load_saved`). La
evaluación de estimaciones no se comparó con datos locales: no hay capturas en el
periodo observado y su paridad con la fórmula está probada con datos temporales.

Research Lab empieza a migrarse por la lista de experimentos. `GET
/research/experiments` y `GET /research/experiments/{id}` exigen el modo Research
local, como la navegación de Streamlit, y leen `experiments` con SQLite en solo
lectura: no crean la tabla ni añaden columnas como hacía `research_lab` al
listar. Una base anterior sin las columnas de entorno devuelve esos campos
vacíos. La lista conserva el orden y los filtros de familia y fase de
`list_experiments` y pagina en el servidor; no devuelve la serie de retornos,
solo si existe. El detalle muestra el entorno registrado (Python, huella de
`uv.lock`, huella de datos y dependencias), la metodología y el número y las
fechas extremas de la serie, sin recalcular nada. Topes: 5.000 experimentos,
16.384 caracteres por campo y 2.000.000 por serie; excederlos devuelve 503 sin
recortar. Las fases se definen ahora en `gabi.domain.research.experiments` y
`research_lab` las reexporta. Las pruebas comparan ambas respuestas con
`research_lab.list_experiments`/`get_experiment` sobre datos temporales.

PSR/DSR y el riesgo de cola de una serie guardada son consultas en modo
Research: `GET /research/experiment-statistics/deflated-sharpe` y `GET
/research/experiments/{id}/tail-risk`. Usan los mismos datos que la página
antigua: N es el número de experimentos con Sharpe de la familia elegida (todos
si no hay familias); asimetría y curtosis salen de la serie si existe, y si no
se usa la aproximación normal; los periodos por año valen 4 y las
observaciones 36 cuando faltan. El horizonte de cola sigue a la frecuencia
registrada. Las fórmulas son `stats_rigor` y `portfolio_metrics` sin cambios,
mediante `infrastructure/legacy/experiments.py`; las pruebas comparan valores
exactos con las expresiones de la página. Son cálculos en memoria sobre una
serie acotada y no escriben. PBO/CSCV no es una consulta: con 16 bloques evalúa
12.870 particiones y tardó unos 28 s con una matriz sintética de 120×5 y otra
de 2.500×4, así que se ejecutará como job explícito.

PBO/CSCV y el bootstrap por bloques de un experimento son ahora los jobs
explícitos `experiment_pbo` y `experiment_bootstrap`, en modo Research para
encolar y para leer. PBO compara de 2 a 20 experimentos con serie guardada:
une las series por fecha y descarta las que no coinciden, exige 16 fechas
comunes y usa `n_splits = min(16, (n // 10) * 2 or 2)` con
`stats_rigor.pbo_cscv`, como el multiselect antiguo. El bootstrap aplica
`block_bootstrap.analyze_sensitivity` con las longitudes preregistradas, la
semilla y las 4.096 réplicas por defecto. Exige al menos 30 observaciones y una
frecuencia con longitudes preregistradas. El benchmark opcional debe tener la
misma frecuencia y exactamente las mismas fechas; si no, se explica el motivo y
no se recorta ni se rellena nada. El artefacto añade la procedencia de cada
experimento (id, modelo, commit y huella de datos) y conserva todas las
réplicas. Como el worker guarda el JSON con claves ordenadas, las réplicas se
guardan como lista de columnas y el orden de los bloques se guarda aparte; el
CSV descargado y las tablas mantienen el orden de la página antigua. Las tablas
de intervalos, fracciones y HAC y los histogramas se calculan en
`application/research/block_bootstrap_view.py`, la presentación pura que tenía
`block_bootstrap_ui`; React solo los dibuja. Con un rango de réplicas por debajo
de la resolución de coma flotante, el histograma usa un único intervalo en vez
de fallar. Las pruebas comparan PBO, auditoría, réplicas, CSV y tablas con las
llamadas antiguas.

El alta manual y el borrado de experimentos son comandos explícitos en modo
Research: `POST /research/experiments` y `POST
/research/experiments/{id}/delete`. El alta valida los campos del formulario
antiguo y construye la misma llamada a `research_lab.log_experiment`: factores
fijos, huella de datos recortada y 0 en Sharpe, Sortino o drawdown guardado como
ausencia. Así se conservan el commit, las versiones de dependencias y la huella
de `uv.lock` que captura el registrador. La escritura pasa por
`infrastructure/legacy/experiment_log.py`, que usa `log_experiment` y
`delete_experiment` sin cambios y devuelve 503 si la configuración del proyecto
no apunta al mismo directorio de datos que la API (la misma guarda que el
worker). Un formulario inválido no crea la base. React pide confirmación antes
de borrar. El backend de pruebas e2e apunta esa configuración a su directorio
temporal.

| Recorrido F0 | Estado F6 | Paso pendiente para equivalencia |
| --- | --- | --- |
| Ranking histórico | Ranking por fecha con cobertura y tabla completa, preparación de datos, resultado posterior y bloques, backtests V1/V2, registro en Research Lab, riesgo de cola, drag fiscal y Fama-French en React, con artefactos y hash | Completado; página Streamlit retirada. |
| Research Lab | Catálogo público, lista de experimentos con su entorno, PSR/DSR, riesgo de cola, PBO/CSCV, bootstrap por bloques, alta manual y borrado en React; auditorías guardadas en Streamlit | Ensayos operativos, artefactos, estadísticas y exportaciones con reglas de reserva. |
| Factor Lab | Motor existente como job y resumen en React, con artefacto completo y hash, quintiles, periodos saltados y glosario; mapa publicado, diagnóstico SIC, cobertura y evaluación explícita de estimaciones en React | Completado; página Streamlit retirada. |
| Blind Forward Validation | Estado y verificación de sellos en React; operaciones y resultados en Streamlit | Alta, rebalanceos y revelación protegidos por API y preregistro. |
| Portfolio Lab | Streamlit | Construcciones y riesgo mediante jobs con costes idénticos. |

Antes de cerrar #68 se comprobarán los 17 recorridos del inventario F0, la
paridad de cálculos y persistencia, la recuperación local y los límites de
memoria/tiempo. Solo entonces se retirarán consumidores y dependencias
Streamlit sin tocar los motores y artefactos publicados.
