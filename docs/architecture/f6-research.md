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

Las auditorías guardadas de Research Lab se consultan en modo Research desde
`GET /research/saved-audits/...`. Son la auditoría retrospectiva de sobreajuste,
el benchmark ajustado por factores, la estabilidad FF5 + Momentum, el
diagnóstico de bloques y la estabilidad histórica del ranking. Cada auditoría
la verifica su lector antiguo sin cambios (`load_audit`/`load_saved`, con sus
huellas SHA-256) mediante `infrastructure/legacy/saved_audits.py`.
`FileSavedAudits` guarda el resultado en memoria hasta que cambian la identidad,
el tamaño o los tiempos de algún fichero de su directorio, con topes de 8 MB
por fichero y 24 MB por auditoría. Una alteración devuelve 503 solo en esa
sección, como el aviso de Streamlit. Una auditoría no publicada se oculta.
Las descargas sirven los ficheros publicados de una lista cerrada y fallan si
cambian durante la lectura. El bootstrap guardado usa la misma presentación
que el job. El benchmark y la estabilidad reutilizan los componentes React del
contraste Fama-French. Medición local, Windows/Python 3.13.7, 20 repeticiones:
primera verificación 0,014 s para sobreajuste (más 2,6 s de importación del
módulo antiguo, una vez por proceso), 0,009 s para benchmark, 0,013 s para
estabilidad, 0,185 s para el bootstrap (3,3 MiB de pico) y 0,215 s para la
estabilidad del ranking (2,6 MiB); las consultas cacheadas tardan entre 0,6 y
8 ms de mediana. Las pruebas comparan los valores con los lectores y las tablas
antiguas, la invalidación al cambiar un fichero y la lista cerrada de descargas.

El registro prospectivo (live ledger) se consulta en modo Research.
`GET /research/live-ledger` verifica la cadena completa y el ancla, como la
página antigua en cada render, pero lee SQLite en solo lectura y fila a fila:
no crea `writer.lock`, no ejecuta el `CREATE TABLE` de `events()` y parsea cada
payload una sola vez. El resultado se guarda en memoria hasta que cambian
`gabi.db`, su WAL o el ancla. Si la lectura cae entre el commit de un escritor y
la actualización del ancla, se repite una vez. El hash canónico, la
verificación y la reproducción de una decisión se han movido sin cambios a
`gabi.domain.research.live_ledger`; `live_ledger` delega en ellos y conserva sus
nombres públicos. El detalle de una decisión comprueba su fila contra el hash
verificado, reproduce scores y ranking desde los bloques congelados y permite
descargar el evento canónico. El rendimiento LIVE_FORWARD es el job explícito
`live_forward_report`, que llama a `live_performance.report` sin cambios para
una versión de modelo. «Guardar evaluación como evento nuevo» es `POST
/research/live-ledger/evaluations`: relee el informe verificado de ese job y
llama a `live_ledger.save_evaluation`, con la misma guarda de directorio de
datos. Rechaza con 409 un ledger no íntegro, un escritor ocupado o una
evaluación con la misma huella que ya esté guardada. Un ledger alterado oculta
las decisiones y muestra el motivo. Las pruebas comparan resumen, reproducción,
informe y evaluación con el módulo antiguo sobre datos temporales y
comprueban que la consulta no escribe. La base local todavía no tiene ledger.
Medición con un ledger sintético de 250 decisiones de 500 empresas (71 MiB),
Windows/Python 3.13.7: la verificación nueva tardó 6,9 s frente a 8,1 s de
`live_ledger.events()`, y las consultas cacheadas 0,2 ms de mediana en 20
repeticiones. El coste crece con el ledger porque cada cambio de la base vuelve
a verificar la cadena completa, como hacía Streamlit en cada render.

La página Streamlit `11_Research_Lab.py` se ha retirado tras comprobar la
equivalencia con los 49 experimentos de la base local. La tabla `experiments`
se copió a una base temporal (`data/gabi.db` solo se leyó y quedó sin cambios)
y allí se ejecutaron el código antiguo y el nuevo. Coincidieron sin diferencias
la lista, los filtros por familia y fase y el entorno de cada experimento; PSR,
DSR, SR*₀ y N en las 36 combinaciones de familia y experimento con Sharpe;
el riesgo de cola de las 29 series guardadas; PBO, combinaciones y logits de
las 2 familias con series comparables; y la auditoría y las réplicas (incluido
el CSV) de los 28 bootstraps elegibles, emparejados con la primera serie de la
misma frecuencia y fechas. Las auditorías guardadas se comparan en las pruebas
con los lectores antiguos sobre los artefactos publicados. El live ledger no se
comparó con datos locales porque la base todavía no tiene registro prospectivo;
su paridad está probada con datos temporales. Se retiran también
`block_bootstrap_ui`, `factor_benchmark_ui`, `factor_stability_ui` y
`rank_stability_ui.render_saved`, que solo usaba esta página, con sus
excepciones de arquitectura y sus pruebas. Las tablas de `block_bootstrap_ui`
se conservan como copia de referencia en `backend/tests/` para seguir
comparando la presentación nueva. `live_ledger_ui`, `rank_stability_ui.render`
y `tail_risk_ui` siguen en uso por el Screener y Portfolio Lab. La historia
publicada no se modifica.

Las validaciones ciegas aplican ahora en el backend las reglas de sus
preregistros. `FileBlindPlans` lee los planes publicados: el de la prueba de
GABI (id 1, #42, `docs/prospective-plan/gabi-id1.json`) y el de la hipótesis de
valor (id 3, #43, `docs/value-hypothesis/preregistro.json`). Verifica sus huellas
con `prospective_plan.plan_hash` y `value_hypothesis.spec_hash` sin cambios y
los guarda en memoria hasta que cambia el fichero. Un plan alterado bloquea con
503 cualquier consulta u orden ciega, en vez de dejar de aplicar sus reglas.
La política es la función pura `disclosure` del dominio:
- Sin preregistro: el rendimiento se revela en la fecha de desbloqueo o si el sello se rompe, como en Streamlit.
- Con preregistro: solo a partir de su primera revisión y calculado hasta la última revisión alcanzada. En el #43 los trimestres posteriores siguen ocultos hasta 2032 y 2036.
- Un sello roto antes de esta regla seguiría visible, porque ocultarlo falsearía lo que ya se vio.

El estado indica el plan, su huella, la próxima revisión y si toca registrar.
El alta (`POST /research/blind-validations`) valida el formulario antiguo y
llama a `blind_validation.create_validation` sin cambios. Romper el sello
(`POST .../{id}/break-seal`) exige motivo y modo Research, y la API lo rechaza
con 403 en las pruebas preregistradas, por decisión del propietario
(2026-10-01). Ambas órdenes usan la misma guarda de directorio de datos que el
resto de escrituras heredadas. Con la base local, las pruebas 1 y 3 aparecen
bloqueadas, ligadas a su preregistro y con la cadena íntegra, y `gabi.db` no
cambia.

Registrar un rebalanceo, calcular el rendimiento revelado y exportarlo a
Research Lab son ahora los jobs `blind_rebalance`, `blind_performance` y
`blind_export`, en modo Research. El worker vuelve a aplicar las reglas en el
momento de ejecutar.
- **Rebalanceo:** solo se registra si toca, con la cadena íntegra y con precios del último cierre (`periodic_tasks.prices_fresh`). En Streamlit las dos últimas condiciones solo desactivaban el botón. El registro siempre es con fecha de hoy y usa `blind_validation.record_rebalance` sin cambios. El resultado nunca incluye posiciones ni precios, solo fecha, número de posiciones y hash.
- **Rendimiento:** solo se calcula si `disclosure` lo permite. `get_status` y `export_to_research_lab` aceptan ahora un corte opcional `as_of`: solo cuentan los rebalanceos anteriores y el último periodo se valora en esa fecha. Sin corte se comportan como antes. Con preregistro, el corte es la última revisión alcanzada. El capital acumulado repite el `cumprod` con ausencias como cero de la página antigua.
- **Exportación:** falla si la validación sigue bloqueada.

Las pruebas comparan rendimiento, acumulados y exportación con las expresiones
antiguas y comprueban el corte en la revisión con datos temporales.

La página Streamlit `13_Blind_Validation.py` se ha retirado. Con una copia
temporal de las tablas ciegas de la base local, el estado nuevo y
`blind_validation.get_status` coincidieron sin diferencias para las pruebas 1 y
3: nombre, estado, desbloqueo, periodos, próximo rebalanceo (2026-12-21),
días hasta el desbloqueo, integridad y revelado. `data/gabi.db` solo se leyó.
El rendimiento no se pudo comparar con datos locales porque ambas pruebas siguen
bloqueadas hasta 2029, como deben. El registro del rebalanceo no se ejecutó con
la base real porque escribiría, y aún no toca. Ambas paridades están probadas con
datos temporales. El aviso de rebalanceo de la portada y las instrucciones de
`docs/prospective-plan/README.md` remiten ahora a Investigación → Validaciones
ciegas; el plan sellado (`gabi-id1.json`) no cambia. `blind_validation` y
`periodic_tasks` siguen en uso por el mantenimiento programado.

Portfolio Lab se ejecuta ahora como el job `portfolio_lab` en modo Research.
Tiene los mismos parámetros que el formulario antiguo: periodo, rebalanceo,
posiciones, capital, esquemas, y modo `validation` o `fast_dev` con 50/100/200
empresas. Llama a `portfolio_lab.run_portfolio_lab` sin cambios. Como los
backtests V1/V2, el periodo se limita al histórico observado del S&P 500
(2010-01-01 a 2025-07-02), al encolar y al leer. Streamlit permitía llegar hasta
hoy y leer precios posteriores al corte de las reservas. El artefacto, con hash
y límites de 200 periodos y 5.000 puntos, guarda por esquema las métricas
diarias, turnover, coste, HHI, tracking error, top-3 de contribución al riesgo,
pesos y contribuciones del último rebalanceo y la curva de capital, además de
los escenarios, los saltados y la curva del SPY. Los esquemas se guardan como
lista para conservar su orden en el JSON de claves ordenadas.
`GET /research/portfolio-lab/{id}` añade el riesgo de cola diario de cada curva
con `returns_from_nav` y `tail_risk_metrics`, como `tail_risk_ui.render_nav`.
React presenta la comparativa, las curvas, la concentración del riesgo y los
stress tests, con la base real o heurística de cada escenario. Las pruebas
comparan el artefacto con la llamada directa al motor sobre datos temporales:
métricas, curvas, pesos, contribuciones, escenarios, saltados y riesgo de cola.

La página Streamlit `14_Portfolio_Lab.py` se ha retirado tras comprobar la
equivalencia con la base local. La llamada directa a `run_portfolio_lab` y el
camino del job coincidieron sin diferencias en métricas, curvas de los seis
esquemas y del SPY, turnover, costes, pesos, contribuciones al riesgo,
escenarios y saltados. Casos: muestra de 200 empresas del 2015-05-02 al
2016-02-02 (2 periodos, 161 s frente a 160 s) y de 100 del 2015-08-02 al
2016-02-02 (1 periodo, 42 s frente a 42 s), con `gabi.db` sin cambios y red
bloqueada. Con la base actual el motor salta casi todos los periodos: lo hace en
cuanto una de las 20 candidatas no tiene precio de entrada, y en 2012-2015
faltan a menudo tickers desaparecidos (DISCA, DTV, WLP, GGP…). Es la misma regla
del motor antiguo. Por eso no se comparó el modo `validation` con el universo
completo, cuyos periodos de prueba se saltaban todos. Se retira también
`tail_risk_ui`, que ya no tiene consumidores, con su excepción de arquitectura.
Streamlit ya no tiene páginas exclusivas de Research; el modo sigue gobernando
los pesos experimentales.

| Recorrido F0 | Estado F6 | Paso pendiente para equivalencia |
| --- | --- | --- |
| Ranking histórico | Ranking por fecha con cobertura y tabla completa, preparación de datos, resultado posterior y bloques, backtests V1/V2, registro en Research Lab, riesgo de cola, drag fiscal y Fama-French en React, con artefactos y hash | Completado; página Streamlit retirada. |
| Research Lab | Catálogo público, lista de experimentos con su entorno, PSR/DSR, riesgo de cola, PBO/CSCV, bootstrap por bloques, alta manual, borrado, auditorías guardadas y registro prospectivo en React | Completado; página Streamlit retirada. |
| Factor Lab | Motor existente como job y resumen en React, con artefacto completo y hash, quintiles, periodos saltados y glosario; mapa publicado, diagnóstico SIC, cobertura y evaluación explícita de estimaciones en React | Completado; página Streamlit retirada. |
| Blind Forward Validation | Estado, sellos y planes preregistrados; alta, rebalanceo, ruptura del sello (prohibida con preregistro), rendimiento hasta la última revisión y exportación en React | Completado; página Streamlit retirada. |
| Portfolio Lab | Job Research con artefacto completo y hash; comparativa, curvas, riesgo de cola, concentración y stress tests en React | Completado; página Streamlit retirada. |

Antes de cerrar #68 se comprobarán los 17 recorridos del inventario F0, la
paridad de cálculos y persistencia, la recuperación local y los límites de
memoria/tiempo. Solo entonces se retirarán consumidores y dependencias
Streamlit sin tocar los motores y artefactos publicados.

## Cierre de F6: auditoría de las páginas Streamlit restantes

Investigación ya no tiene páginas en Streamlit. Antes de retirar Streamlit se
compararon las 12 páginas restantes y la portada con React y la API (2026-10-01).
Las fases F2-F5 cubrieron sus recorridos principales, pero quedan funciones sin
sustituto:

| Página | Sin equivalente en React | Propuesta |
| --- | --- | --- |
| Screener, Mi cartera, Ficha | Evidencia por candidata (`evidence_confidence`): Top-20 con confianza BAJA/MEDIA/ALTA, motivos a favor y en contra, factores con Holm, estabilidad SIC y descarga | Hecho: `GET /evidence` y `/companies/{symbol}/evidence` |
| Screener | Estabilidad del ranking actual ante cambios de 1-2 puntos en los pesos (`rank_stability.analyze`) | Hecho: `GET /ranking/stability` (1,3 s con la base local; no hace falta un job) |
| Screener | Avisos de cobertura por bloque con umbral configurable | Hecho: `GET /ranking/coverage` sobre todo el ranking, encima de la tabla de Mercado |
| Screener | Seguimiento de rankings guardados: progreso frente al SPY, curva, detalle por empresa, 6 y 12 meses y cambio de nombre | Hecho: `GET /market/snapshots/{id}/progress` y `POST .../rename`, en el Signal Monitor |
| Ficha | Historial de sorpresas de resultados y estimaciones de consenso, con su sincronización | Hecho: `GET /companies/{symbol}/research` y job `company_sync` |
| Ficha | Métricas informativas no puntuadas | Hecho: grupo propio en la ficha |
| Configuración | Guardar las claves FRED, Tiingo y Nasdaq Data Link; tamaño del universo al actualizar; resumen de fallos y reintento de los fallidos | Hecho: job `data_update` (50, 150 o todo el universo; reintento forzado de los fallidos) y `POST /administration/keys/{source}` (también FMP), que nunca devuelve la clave |
| Calidad de los datos | Resumen del universo, errores recientes, cobertura por bloque, última observación FRED, procedencia e identidad de una empresa y diagnóstico de identidades | Hecho: `/administracion/calidad` con el job `data_health` (el código antiguo crea el esquema al leer, así que no puede ir en un GET); la cobertura por bloque reutiliza `GET /ranking/coverage`. Con la base local: universo 10 s, empresa 0,1 s, identidades 1,8 s |
| Calidad de los datos | Explorador del archivo histórico 1996-2016 (miembros y precios) | Hecho, solo 2010-2015: ámbitos `archive`, `archive_members` y `archive_prices` del job `data_health`; fechas anteriores a 2010 rechazadas y cobertura trimestral recortada (decisión del propietario, 2026-10-01) |
| Carteras simuladas | Backtest de cruce SMA de un ticker | Retirar: ejercicio aislado sin relación con la hipótesis (decisión del propietario, 2026-10-01) |
| Carteras simuladas | Botones de descarga de precios de un ticker o cartera | Usar el job `symbols` existente |
| Aprender | Tutorial extenso | Hecho: las cuatro pestañas en `/cartera/aprender`; las definiciones de métricas pasan de `ui_helpers` a `domain/market/metric_info.py` y React las lee de `GET /learn/metrics`, que marca las 13 que puntúan (decisión del propietario, 2026-10-01) |
| Portada | Avisos de rebalanceo ciego próximo y del análisis del #44 | Hecho: `GET /notices` (solo lectura, 0,1 s, igual que `periodic_tasks.due_soon` y `smallmid_state` con la base local), mostrado en `/mercado` junto al aviso legal de la portada |

La retirada de Streamlit (páginas, helpers `_ui`, `ui_helpers` y la dependencia)
queda pendiente hasta cubrir o descartar explícitamente cada fila.

Durante la auditoría se encontró que el ranking de React fallaba con la base
local. Cada lote de 16 empresas leía el histórico completo de precios, que tras
el relleno profundo llega a 16.292 sesiones por empresa, y superaba el
presupuesto de 160.000 filas. Los indicadores de riesgo usan todo el histórico,
igual que el Screener antiguo, así que no se acota la ventana. Los lotes se
forman ahora con un recuento previo por empresa: son consecutivos, de hasta 16
empresas y sin superar el presupuesto. Con la base local el ranking nuevo
coincide exactamente con `screener.build_screener_table` en las 503 empresas
(scores, cobertura, volatilidad, drawdown, PER y RSI). Tarda 42,6 s en frío
frente a 32,8 s del antiguo, con 137 consultas, y `gabi.db` no cambia.

La evidencia por candidata y la estabilidad del ranking actual se consultan en
`GET /evidence` (Top-20; `frozen=true` usa los pesos congelados en cualquier
modo, como hacía «Mi cartera»), `GET /companies/{symbol}/evidence`, su descarga
JSON y `GET /ranking/stability`. Llaman a `evidence_confidence.build` y
`rank_stability.analyze` sin cambios, sobre el ranking ya cacheado y con los
pesos del modo. No descargan ni escriben. El resultado se guarda en memoria por
revisión del ranking y pesos, con una entrada por tipo. Las respuestas proyectan
lo que mostraba Streamlit: Top-20 por score con cobertura de al menos el 70 %,
motivos, factores, estabilidad SIC y fases. Los bloques técnicos solo se envían
en modo Research. La tabla de estabilidad muestra el Top-20 en Investor; en
Research añade todas las empresas, las métricas y los pesos de cada
perturbación. Con la base local, la evidencia de las 503 empresas tarda 5,5 s y
ocuparía 55 MB en JSON, por eso no se envía completa. La estabilidad tarda
1,3 s. React solo hace estas consultas al abrir su sección. Durante la
migración se encontró que `evidence_confidence.build` fallaba con datos reales,
también en Streamlit: el hash canónico del ledger no admitía la fecha
`next_earnings_date` (`datetime.date`). `safe` la convierte ahora a ISO. Ningún
hash publicado cambia, porque antes esos valores producían una excepción. La
captura diaria del registro prospectivo, que calcula la misma huella, queda
corregida también.

El seguimiento de los rankings guardados está en el Signal Monitor de React.
`GET /market/snapshots/{id}/progress` devuelve el progreso hasta hoy de la cesta
equiponderada frente al SPY, el detalle por empresa, la curva base 100 y los
resultados a 6 y 12 meses. `POST /market/snapshots/{id}/rename` cambia el nombre
con la regla antigua (1-80 caracteres). `evaluation` separa `progress_for` y
`price_curve_for` de `snapshot_progress` y `snapshot_price_curve`, que conservan
su comportamiento; las nuevas reciben lectores acotados y de solo lectura
(ventana de ±7 días de `_adjusted_at`, último precio de las candidatas e
historial desde una semana antes de la fecha guardada). Son rankings en vivo,
no un histórico reservado, así que no hay corte de periodo, como en Streamlit.
Con la base local, los tres rankings guardados coinciden exactamente con
`snapshot_progress` y la curva antigua (unos 0,2 s cada uno) y `gabi.db` no
cambia.

La ficha de React incluye ahora lo que faltaba de la página antigua:
- **Catalizadores:** todos los próximos eventos fechados (resultados, ex-dividendo y pago), parseados con `events_calendar.parse_corporate_events` sobre el registro de fundamentales cacheado.
- **Métricas informativas no puntuadas:** beta calculada, alfa, meses positivos, beta de Yahoo, rentabilidad por dividendo y volumen.
- **Sorpresas y estimaciones:** el historial de sorpresas de resultados y la última captura de consenso del trimestre con su revisión a 90 días (`estimates.compute_revision` sin cambios). Se leen en solo lectura con topes de 200 y 5.000 filas, sin crear las tablas que antes inicializaba la lectura.
- **Filings:** los cambios del último 10-K y 10-Q frente al anterior, con la misma comparación sobre hechos SEC cacheados que usa el Signal Monitor.

`GET /companies/{symbol}/research` y `/filing-changes` no descargan nada. Las
sincronizaciones de sorpresas y estimaciones, que sí usan la red, son el job
explícito `company_sync` y devuelven el motivo si fallan. Con la base local,
AAPL, MSFT y NVDA coinciden con `get_earnings_surprises`,
`latest_estimate_snapshot`, `revision_since` y `filing_tracker.compare_filings`
(0,01-0,23 s por consulta) y `gabi.db` no cambia.

