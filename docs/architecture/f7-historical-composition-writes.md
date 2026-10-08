# Composición histórica y escrituras de auditoría (F7.7)

Los loaders `_operational`/`_archive` de `historical_membership` delegan en
`application/research/historical_composition.py` y `LocalHistoricalComposition`.
Las reglas de snapshots, conflictos e intervalos semiabiertos viven en
`domain/research/historical_membership.py`. Se mantienen las correcciones de
etiquetas, las salidas/reentradas y los límites de cobertura; no se incorpora
el universo actual ni se transforma una discrepancia en evidencia acreditada.

El loader recibe la ruta SQLite, el CSV, el ledger revisado y el reloj. El CSV
se procesa mediante un stream con presupuesto de bytes y un límite de filas;
no se reserva el presupuesto entero como buffer. Se permiten 50.000 snapshots,
16 MiB y campos de 1 MiB. El ledger también queda limitado a 1 MiB y conserva
su política de fecha y anchor. El exceso falla, sin devolver cobertura truncada.

La composición archivada y el snapshot vigente por fuente se consultan con
`mode=ro`, `query_only` y transacción de lectura. Las tablas o fuentes ausentes
no se inicializan. No hay caché: cada operación observa el CSV/ledger y las
revisiones comprometidas en SQLite. Las consultas independientes de composición,
comparación e identidad no prometen una revisión global única.

## Escrituras explícitas y lecturas de compatibilidad

Todos los escritores de `historical_archive` delegan en casos de uso de
`application/research/historical_archive.py` y `SqliteHistoricalArchiveWrites`:
fuentes, composición, candidatos, chunks de precios, hechos SEC, observaciones
de filing e intervalos acreditados. Los registros se preparan antes de escribir;
se conservan claves, normalización, JSON, procedencia, precios nominales y
semántica de reejecución (`IGNORE` para el precio de una revisión fijada).

`historical_price_policy.record_series` y `record_terminal` comparten los casos
de uso de `historical_accreditation.py`. Requisitos de evidencia, tiers, límites
de negociación, ajustes y consideración económica viven en
`domain/research/price_accreditation.py`. La auditoría reutiliza su comparación
de rendimientos; no mantiene una segunda fórmula. El adaptador verifica dentro
de la transacción los conflictos de CIK y las series acreditadas concurrentes,
incluida la excepción existente entre productores de periodos distintos.

`historical_price_audit` delega las eliminaciones de procedencia y el reemplazo
de eventos en ese escritor, con ruta/reloj explícitos. La sucesión reemplaza
el evento desconocido y guarda el nuevo evento en la misma transacción. No hay
cambios de configuración por operación. La fachada conserva la restricción
histórica de `promote` a la base configurada; los puertos nuevos no usan ajustes
globales.

Cada importación usa WAL y una transacción `BEGIN IMMEDIATE`; el DDL se ejecuta por
sentencias, sin el commit implícito de `executescript`. El alta del emisor y
la doble escritura de hechos/observaciones se revierten conjuntamente. La
importación de una lista de filings ahora es atómica para toda la lista: un
error no deja los filings iniciales importados. El reemplazo de intervalos
conserva la revisión anterior si falla una fila. Esta mejora de efectos no
modifica los registros de una importación correcta ni su resultado financiero.

Las fachadas `historical_archive` y `historical_price_policy` también retiran
su SQL de consulta. `SqliteHistoricalArchiveReads` limita cada resultado a
25.000 filas, 16 MiB y campos de 1 MiB. Una lectura estricta comparte una
transacción para procedencia, eventos y precios. Conserva prioridad Yahoo,
fronteras inclusiva/exclusiva, atributos, ausencia de stitching/fill y rechazo
de eventos terminales o sesiones incompletas. No crea la base ni el esquema.

## Validación y medición

`fixtures/historical_writers_migration.json` captura las cuatro fachadas antes
de esta extracción. Trece pruebas nuevas comparan registros completos,
idempotencia, atributos, errores y composición contra ese código. Comprueban
límites, ausencia de red/conexiones legacy, lecturas sin creación/modificación,
observación de revisiones y rollback de acreditaciones, hechos, intervalos y
sucesiones. Las pruebas existentes de composición, archivos, periodos y
auditorías siguen verificando los criterios de acreditación.

Validación realizada: 1.774 pruebas Python correctas, más comprobaciones finales
de 68 pruebas de escritores/consumidores y 21 de loaders/paridad. Arquitectura
backend (incluida comparación del baseline con `HEAD`), arquitectura frontend
y sus nueve pruebas correctas; mypy no añade diagnósticos a los 25 históricos
de motores congelados. Verificados los tres motores CI y los 18 archivos
publicados/configuraciones. Ruff comprueba los 576 archivos Python versionados
y nuevos de código/tests/scripts. `ruff check .` también encuentra copias y
fixtures de anteriores directorios temporales pytest en este workspace; esas
copias no se alteran para conseguir un resultado limpio. `git diff --check`
es correcto. No se amplían las excepciones de arquitectura.

Medición reproducible: `.venv/Scripts/python.exe scripts/measure_f7_historical_writers.py`.
Windows/Python 3.13; 1.000 snapshots sintéticos con 500 símbolos cada uno,
cuatro ejecuciones por variante y destinos temporales separados para escritura.
Se comprueban paridad exacta de frames/fronteras y todas las filas persistidas.
No se abre `data/`, no hay descargas ni holdouts. Medición concurrente con tests;
los tiempos describen esta ejecución, no un SLA.

| Flujo | Primera ejecución anterior → nueva (s) | Mediana posterior (s) | Pico Python (MiB) | Conexiones | SELECT | Filas entregadas |
| --- | --- | --- | --- | --- | --- | --- |
| Composición archivada | 0,0389 → 0,0696 | 0,0326 → 0,0724 | 3,0749 → 3,0215 | 1 → 1 | 3 → 3 | 1.002 → 1.007 |
| CSV operativo | 0,0680 → 0,1100 | 0,0622 → 0,1201 | 1,0201 → 1,0155 | 0 → 0 | 0 → 0 | 0 → 0 |
| Acreditación Tier A | 0,0437 → 0,0216 | 0,0129 → 0,0072 | 0,0073 → 0,0162 | 2 → 1 | 4 → 4 | 0 fría / 1 posterior |

Las cinco filas adicionales de lectura son inventario de tablas. Las nuevas
comprobaciones de límites tienen coste; no se presenta la extracción como una
aceleración de los loaders. La acreditación utiliza una conexión/transacción,
frente a dos operaciones previamente comprometidas por separado. Los picos
miden asignaciones Python, no RSS. La primera acreditación crea sus tablas;
las posteriores actualizan el mismo intervalo.

## Alcance que continúa pendiente

[F7.8](f7-historical-runners.md) migra la coordinación de composición,
comparaciones, hash/importación fijada, runners de precios, cálculos y lecturas
de identidad retrospectiva, exportaciones y respaldo operativo por ticker.
Los archivos y cachés de evidencia se extraen en [F7.9](f7-historical-issuer-files.md).
Permanecen los adaptadores de descarga de evidencia, las acciones
de ingesta/escaneo de identidad y el contexto de compatibilidad
`accredited_periods`. La promoción sigue sustituyendo el productor y
acreditando cada intervalo por separado; no es una transacción global de
la auditoría. No se declara terminada la migración de todos los consumidores
históricos ni se toca ningún motor sellado o configuración publicada.
