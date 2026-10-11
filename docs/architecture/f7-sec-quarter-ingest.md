# Selección e ingesta del archivo SEC (F7.13)

Continúa [F7.10](f7-sec-archive-download.md) y [F7.11](f7-sec-bulk-import.md):
la selección de qué descargar, la coordinación por trimestre con checkpoints y
la recuperación de instancias XBRL originales salen de las fachadas.

- `domain/research/sec_bulk.py`: claves y URL trimestrales, URL de instancia,
  formularios por modo, instancias pendientes e interpretación de hechos de una
  instancia ya decodificada (`instance_facts`).
- `domain/research/identity_instances.py`: `select_cover_filings`, la muestra de
  tres filings por mandato candidato más los de intervalos sin resolver.
- `application/research/sec_quarter_ingest.py`: `ingest_quarters` (con o sin
  checkpoints), `nominated_missing`, `period_ciks`, `cover_filings` y
  `recover_instances`. Recibe descarga, importación, lector, checkpoints y log.
- `infrastructure/storage/sec_quarter_ingest.py`: `decode_instance` (lxml sin
  entidades ni red), `SqliteSecIngestSelection` de solo lectura,
  `JsonQuarterReport` y `backup_once`.

Fachadas: `sec_history.target_ciks`, `run_bulk`, `recover_instances` y
`parse_instance`; `historical_identity_audit.import_nominated_filings`,
`import_period_filings`, la selección de `fetch_candidate_instances`, los
objetivos de `annual_report_symbol_evidence` y los CIK de
`fetch_issuer_name_histories`. Mantienen firmas, rutas, mensajes impresos y
retornos. Ambas fachadas dejan de importar `storage`; `historical_identity_audit`
deja `identity` y `sec_history` deja `sqlite3`. El inventario baja en cuatro
dependencias.

## Contratos conservados

- Mismos trimestres, URL, CIK por consulta, orden de descargas e importaciones,
  forma del informe y truncado de errores a 180 caracteres. `run_bulk` y la
  recuperación de instancias saltan claves completas y guardan cada resultado
  antes de la siguiente; las importaciones por periodo/nominadas no tienen
  checkpoints y se detienen en el primer error, como antes.
- Los informes JSON conservan contenido y saltos de línea de la plataforma.
  Ahora se escriben en un temporal y se reemplazan de forma atómica: un fallo
  de disco deja el informe anterior, no uno truncado.
- La copia `before_validation.db` se toma una vez. Si la base no existe se crea
  una copia vacía, como hacía la conexión legacy, sin crear la base de origen.
- La interpretación XBRL conserva identificador del emisor, exclusión de
  segmentos/escenarios, contextos sin periodo, unidades simples, namespaces
  `us-gaap`/`dei`, valores no finitos, conflictos y validación de fechas.

## Cambios de efecto

- Las selecciones abren `mode=ro`/`query_only` con una transacción de lectura y
  ya no ejecutan `ensure_schema` antes de consultar. Las importaciones siguen
  creando y migrando su esquema dentro de su propia transacción (F7.11).
- Una tabla ausente es ausencia de evidencia: CIK objetivo vacío, filings
  vacíos y accesiones sin hechos vacías. Antes algunas consultas fallaban con
  `OperationalError`. `recover_instances` sigue fallando sin presentaciones
  indexadas, ahora con `ValueError`.
- Presupuestos: 2.000.000 filas y 512 MiB por consulta, 64 KiB por campo; un
  exceso falla sin truncar. No hay caché: cada acción observa la última revisión.

La coordinación paralela y con ritmo de las descargas de covers, la recuperación
de Company Facts por CIK y el agregado small/mid siguen en sus fachadas.

## Validación y medida

Referencia `c324aabadf3c7b517129f5cd55ffff880921d865` en
`fixtures/sec_quarter_ingest_migration.json`. `test_sec_quarter_ingest_migration.py`
(23 pruebas) ejecuta las funciones capturadas y las nuevas sobre la misma base
temporal con descargas e importaciones simuladas: CIK objetivo, `run_bulk` con
informe previo, fallos y copia; instancias en los tres modos con errores de red
y XML; importaciones nominadas/por periodo con su error de ZIP; selección de
covers con y sin prioridad en dos periodos; parseo XBRL y sus errores. Comprueba
solo lectura, base ausente sin creación, límites y reemplazo atómico. Dos
mutaciones deliberadas (muestra de covers y trimestres) hacen fallar ocho pruebas.
`test_identity_instances_migration.py` pasa explícitamente `storage`/`identity`
al código capturado, que antes tomaba de los globales de la fachada.
Validación del 2026-10-11: suite Python completa de 1.891 pruebas correcta.

Medida: `.venv/Scripts/python.exe scripts/measure_f7_sec_quarter_ingest.py`.
Windows/Python 3.13, 600 emisores y 16.800 presentaciones sintéticas; ambas
variantes comparten la regla pura, así que se mide el acceso a datos. Paridad
exacta y cero descargas.

| Selección | Frío anterior → nuevo (s) | Mediana caliente (s) | Pico Python (MiB) | SELECT |
| --- | --- | --- | --- | --- |
| CIK objetivo | 0,0009 → 0,0016 | 0,0008 → 0,0015 | 0,06 → 0,08 | 1 → 2 |
| Selección de covers | 0,0303 → 0,0586 | 0,0299 → 0,0599 | 4,16 → 4,16 | 3 → 6 |
| Instancias pendientes | 0,0357 → 0,0402 | 0,0275 → 0,0389 | 2,71 → 2,71 | 2 → 4 |

Cada consulta abre su conexión de solo lectura e inventaría tablas, por eso hay
más SELECT y unos milisegundos más. Estas acciones son explícitas y largas
(descargas); el cambio busca no escribir al seleccionar, no velocidad.
