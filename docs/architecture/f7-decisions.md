# F7.4: retirada de `decision_engine` (#90)

Las reglas de elegibilidad, selección, reservas para posiciones no revisables,
límites, optimizadores y etiquetas de decisiones tienen una implementación en
`domain/portfolio/decisions.py`. El día del plan es un argumento obligatorio;
el dominio no lee SQLite, configuración global ni el reloj.

API y worker comparten el caso de uso `application/portfolio/decisions.py` y la
serialización de `infrastructure/serialization/decisions.py`. Portfolio Lab usa
el mismo optimizador de dominio. Los planes existentes conservan el esquema
`decision_runs`, política, posiciones, fechas y JSON; los cálculos de progreso
ponderado y curva usan `domain/portfolio/decision_progress.py`, introducido en F5.
No se cambia el contrato HTTP ni la interpretación de la política experimental.

Se elimina `gabi/decision_engine.py`, su puente legacy y su excepción de tipos.
No quedan consumidores de ese nombre ni manifiestos sellados que exijan la
fachada. Las interfaces Python internas antiguas se sustituyen por el dominio,
caso de uso y repositorio ya utilizados por la API; el inventario baja a 81.

`SqliteDecisions` recibe ruta y reloj explícitos. Sus lecturas de planes antiguos
calculan el nombre alternativo sin ALTER/UPDATE. Renombrar es una escritura
explícita y añade la columna `name` si falta, sin perder los demás campos.
Guardar conserva la migración e idempotencia por job de F5.

## Evidencia y límites

Las referencias `decision_rules_migration.json` y `decision_progress_migration.json`
guardan resultados y hash LF de la implementación anterior `486942a`, sobre
tablas/series sintéticas y SQLite temporal. Siete escenarios comprueban reglas,
scores, ausencias, riesgo y capital reservado; se compara también progreso real
ponderado con la misma ventana de datos. Los tests previos de optimización,
límites, turnover, planes, persistencia, API/jobs y migraciones usan ahora los
destinos nuevos. Hay pruebas de parámetros temporales obligatorios, ausencia
de mutación de entradas, relojes/rutas independientes y consultas sin escritura.

El acceso de API/worker ya era acotado en F5 (756 precios para generar y ventana
desde el origen para progreso). Este cambio conserva ese acceso y no introduce
caché ni afirma una mejora de rendimiento. Se mantienen los límites de F5 y su
invalidación por revisión de datos. La curva presentada conserva el límite de
500 puntos definido por su contrato; no se modifica la fórmula de ponderación.

La política sigue siendo experimental, distinta de la hipótesis Top-20 congelada.
No se recalculan estudios, consultas ciegas ni evidencia publicada. Los 18
motores/configuración congelados y sus artefactos conservan bytes y hashes.
