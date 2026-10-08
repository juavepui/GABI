# F7.10: descarga y procedencia del archivo SEC

`application/research/sec_archive_download.py` coordina la acción explícita de
descarga con puertos de archivos, procedencia, fuente por chunks y reloj.
`infrastructure/storage/sec_archive_download.py` implementa archivos y SQLite
con rutas explícitas. Ninguno importa módulos planos ni ajustes globales.

La fachada `sec_history.download(url, path)` conserva su retorno `Path` y
conecta las dependencias por operación. El transporte HTTP existente permanece
en una función pequeña de compatibilidad: mismos headers, espera de 0,15 s,
timeouts `(20, 90)`, errores requests y chunks de 1 MiB. Los consumidores de
frames, submissions, informes y covers usan ya el mismo caso de uso a través
de esa interfaz. No se añade un import de proveedor a la fachada ni se amplía
el inventario de excepciones; se respeta ADR 0003.

## Contrato y efectos

- Un archivo presente evita toda llamada a la fuente y toda espera de red.
- Cada acción verifica SHA-256 y tamaño mediante una pasada en streaming. No
  hay caché de hashes: una revisión local se detecta en la siguiente acción.
  Este coste pertenece a la descarga explícita, nunca a una consulta/render.
- La primera procedencia por URL conserva hash, tamaño y fecha. Repetirla es
  idempotente; un hash distinto falla y conserva la fila anterior. La consulta
  y el alta se ejecutan en una transacción `BEGIN IMMEDIATE`, también entre
  trabajadores concurrentes. No hay mutación global por petición/job.
- La escritura usa un temporal único junto al destino y reemplazo atómico.
  Un fallo de red, disco o presupuesto cierra el iterador y elimina el temporal;
  no registra evidencia parcial ni reemplaza un destino con contenido parcial.
- El presupuesto configurable por adaptador es de 4 GiB por archivo, tanto
  descargado como cacheado; superar el límite falla sin truncar. Los archivos
  grandes se procesan por chunks, sin cargarlos completos en memoria.
- Solo se inicializa `sec_archive_files`. Descargar ya no inicializa ni migra
  `sec_bulk_submissions`/`sec_bulk_facts`; sus importaciones explícitas siguen
  siendo responsables de esos esquemas. Una descarga fallida no abre SQLite.

Archivo y SQLite no forman una transacción conjunta. Si falla el registro tras
completar el archivo, este queda cacheado y la siguiente acción puede registrar
su procedencia sin descargarlo de nuevo, como en la implementación anterior.
El reemplazo atómico evita archivos parciales, pero no reserva un destino frente
a dos descargas simultáneas; la procedencia por URL sí se serializa en SQLite.

## Paridad y medición

`sec_archive_download_migration.json` captura la función anterior. Las pruebas
temporales comparan contenido, URL, hash, bytes, fecha, retorno y llamadas HTTP;
comprueban idempotencia, revisión conflictiva, aislamiento de rutas, registro
concurrente, presupuesto y fallos de streaming. No usan fuentes ni bases reales.
También verifican la reanudación sin red tras fallar SQLite con un archivo
ya descargado completamente.

Suite completa: 1.808 pruebas correctas, con nueve warnings preexistentes;
ocho pruebas finales del nuevo adaptador también correctas.
Arquitectura backend sin ampliar excepciones, arquitectura frontend y sus
nueve pruebas correctas. Mypy no añade diagnósticos a los 25 históricos exactos
de motores congelados. Los tres motores CI y los 18 motores/configuraciones
publicados conservan sus hashes. Ruff pasa en los 596 archivos Python de
código, tests y scripts; el chequeo raíz sigue encontrando errores en copias
temporales de pytest del workspace, que no se alteran. `git diff --check` correcto.

Medición: `.venv/Scripts/python.exe scripts/measure_f7_sec_archive_download.py`.
Windows/Python 3.13, 32 archivos sintéticos ya cacheados de 256 KiB (8 MiB),
cuatro ejecuciones por variante, filas de procedencia exactamente iguales.
Medición concurrente con tests; memoria Python, no RSS. Incluye una lectura
final de comprobación (33 conexiones y 33 SELECT por ejecución).

| Variante | Primera ejecución (s) | Mediana posterior (s) | Pico Python (MiB) |
| --- | --- | --- | --- |
| Fachada anterior | 0,4063 | 0,2583 | 0,2658 |
| Caso de uso y adaptadores | 0,3972 | 0,2694 | 1,2616 |

La nueva variante evita inspeccionar el esquema de hechos (32/64 filas leídas
frente a 256/288), pero la transacción explícita y hash por chunks tienen coste.
Ambas variantes usan WAL y timeout de 30 s. Esta extracción no demuestra una
aceleración ni menor memoria.

## Pendiente

Permanecen la selección/coordinación de descargas en las fachadas de evidencia,
el transporte HTTP de compatibilidad y las acciones de ingesta/escaneo de
identidad. [F7.11](f7-sec-bulk-import.md) extrae la importación trimestral
SUB/NUM; su selección de CIK y checkpoints siguen en compatibilidad.
También siguen pendientes el agregado
small/mid, las lecturas generales de `storage` y el contexto de compatibilidad
de `historical_pit.accredited_periods`. No se declara completada F7 ni #60.
