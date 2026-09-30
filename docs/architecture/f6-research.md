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
sin escribir. Quedan en Streamlit el contraste Fama-French, el drag fiscal, el
riesgo de cola y la preparación de datos.
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
de los cinco recorridos de Investigación y la pestaña de backtest SMA heredada.

| Recorrido F0 | Estado F6 | Paso pendiente para equivalencia |
| --- | --- | --- |
| Ranking histórico | Ranking por fecha, backtests V1/V2 y su registro en Research Lab como jobs Research en React, con artefacto y hash | Fama-French, drag fiscal, riesgo de cola y preparación explícita de datos. |
| Research Lab | Catálogo público en React; operaciones antiguas en Streamlit | Ensayos operativos, artefactos, estadísticas y exportaciones con reglas de reserva. |
| Factor Lab | Motor existente como job y resumen en React, con artefacto completo y hash, quintiles, periodos saltados y glosario; mapa publicado, diagnóstico SIC, cobertura y evaluación explícita de estimaciones en React | Verificar el recorrido con la base local y retirar la página Streamlit y su excepción. |
| Blind Forward Validation | Estado y verificación de sellos en React; operaciones y resultados en Streamlit | Alta, rebalanceos y revelación protegidos por API y preregistro. |
| Portfolio Lab | Streamlit | Construcciones y riesgo mediante jobs con costes idénticos. |

Antes de cerrar #68 se comprobarán los 17 recorridos del inventario F0, la
paridad de cálculos y persistencia, la recuperación local y los límites de
memoria/tiempo. Solo entonces se retirarán consumidores y dependencias
Streamlit sin tocar los motores y artefactos publicados.
