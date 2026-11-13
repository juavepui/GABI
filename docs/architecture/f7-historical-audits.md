# Auditorías históricas sin HTTP, hilos ni SQL en las fachadas (F7.21, #131)

Las auditorías históricas de emisores y precios ya delegaban sus cálculos y lecturas
(F7.7–F7.13). Esta entrega retira lo que quedaba de coordinación e I/O en las fachadas:

| Fachada | Antes | Ahora |
| --- | --- | --- |
| `historical_identity_audit.fetch_candidate_instances` | Pool de 4 hilos, marcapasos con `threading.Lock`, reintentos con `requests.HTTPError` | `application/research/sec_cover_downloads.py`: `pending_covers` (límite, caché, orden por fecha de presentación), `Pacer` y `download_covers` con reloj, espera, descarga, clasificación de errores y pool inyectados |
| `historical_issuer_evidence.fetch_frames` / `fetch_submissions` | Bucles con `requests` e `identity` | `application/research/historical_issuer_evidence.py` sobre un puerto `SubmissionFiles` (existencia, descarga con procedencia, lectura) |
| `historical_issuer_evidence.fetch_report` / `fetch_annual_report` | URL construida a mano | `domain/research/sec_bulk.instance_url`; descarga con URL/SHA-256 en `sec_archive_files` como antes |
| `historical_tiingo._Archive.pinned` | `storage.get_connection` + `executescript(SCHEMA)` | `infrastructure/storage/historical_prices.pinned_files`: solo lectura, sin crear esquema; base ausente = nada fijado |
| `sec_history` | `requests` y `lxml` solo para tipos de error | `providers.sec_archive.REQUEST_ERROR` y `storage.sec_quarter_ingest.XML_ERROR` |
| `historical_price_audit` | `sqlite3` para un `_series` sin usos | retirado |
| `historical_data_audit.py` | `connect_readonly` sin importadores | retirado; el comando es `gabi_cli research historical-data-audit` |

## Ritmo y errores

- Un solo `Pacer` por ejecución reparte los arranques entre los cuatro hilos: uno cada
  0,25 s (4/s), reintentos incluidos, por debajo del límite de 10/s de la SEC. El
  proveedor `SecArchiveChunks` mantiene su pausa de 0,15 s por petición, como antes.
- El pool es `infrastructure/jobs/sec_batch.run` (1–4 hilos), expuesto por
  `providers.sec_archive.parallel` para que la fachada no dependa de `jobs`.
- 429/500/502/503/504 se reintentan hasta tres intentos con espera de 1 s y 2 s; el
  resto de errores HTTP, de transporte, `OSError` y `ValueError` se cuentan como
  fallo del cover y se registran. Cualquier otra excepción se propaga, como antes.
- Frames: un 404 de la SEC es «no publicado»; otro error HTTP o de transporte aborta.
  Submissions: los fallos son por CIK y el lote continúa.

Inventario: −10 dependencias y un módulo plano menos (74): `concurrent.futures`,
`requests` (tres fachadas), `lxml`, `gabi.identity`, `sqlite3`, `gabi.storage` y la
entrada de `historical_data_audit`. `historical_issuer_evidence` e
`historical_price_audit` figuran en la huella de `historical_revalidation`
(véase [F7.20](f7-historical-core.md)): editar estos archivos invalida las cachés
locales no publicadas de esas validaciones; los resultados publicados no cambian.

## Validación y medida

`fixtures/historical_audits_migration.json` captura `historical_identity_audit`,
`historical_issuer_evidence`, `historical_tiingo` y `sec_history` de
`c324aabadf3c7b517129f5cd55ffff880921d865`. `test_historical_audits_migration.py`
compara con el código capturado:

- covers: 36 combinaciones (tres guiones de respuestas SEC × límites 0/2/50 × dos
  periodos × prioridad de no resueltos) con informe, intentos por URL, esperas,
  mensajes y archivos; propagación de errores inesperados; límite negativo sin leer;
- frames (404, 500, transporte) y submissions (páginas en los límites de la ventana,
  CIK distinto, JSON inválido, errores de transporte y disco, error inesperado);
- URL y ruta de los documentos 10-K y 8-K;
- hashes fijados de Tiingo sin crear esquema ni modificar la base.

Nueve mutaciones deliberadas (estados reintentables, intervalo, límite, espera,
404, los dos extremos de la ventana de presentación, comprobación de CIK y lectura
fijada) hacen fallar pruebas. `test_historical_runners_migration` inyecta el
`connect_readonly` capturado al ejecutar la auditoría de precios original.

Medida: `.venv/Scripts/python.exe scripts/measure_f7_historical_audits.py`.
Windows/Python 3.13, 5.000 hashes fijados y 400 candidatos (1.200 covers), red y
tiempo simulados, resultados idénticos. Dos ejecuciones:

| Flujo | Anterior (s) | Nuevo (s) |
| --- | --- | --- |
| Hashes fijados Tiingo (mediana de 20) | 0,0030 / 0,0021 | 0,0029 / 0,0023 |
| Covers, primera pasada | 0,589 / 0,535 | 0,498 / 0,663 |
| Covers ya en caché (mediana de 5) | 0,124 / 0,133 | 0,117 / 0,131 |

Sin cambio apreciable: la lectura fijada ya no crea esquema y abre la base en solo lectura.
