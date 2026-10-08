# F7.11: ingesta trimestral del archivo SEC

`sec_history.import_quarter(path, source_url, ciks, facts=...)` conserva su
interfaz y delega en `application/research/sec_bulk.py`. El caso de uso recibe
lector, repositorio y conjuntos de tags/unidades explícitos. Las reglas de
selección e interpretación SUB/NUM están en `domain/research/sec_bulk.py`.
La lectura ZIP/CSV y SQLite se conectan en `infrastructure/storage/sec_bulk.py`.
La configuración solo se resuelve en la fachada, por operación.

Los flujos legacy de importación de CIK nominados, importación por periodo y
`run_bulk` usan ya esa misma implementación mediante su interfaz existente.
No se amplía el inventario de excepciones ni se modifican motores congelados.

## Contrato conservado

- SUB conserva CIK rellenado a diez posiciones, nombre, SIC, formulario,
  fecha, aceptación, ejercicio, periodo, instancia y URL. Se seleccionan
  10-K, 10-Q y sus enmiendas para los CIK recibidos.
- NUM conserva fechas SEC redondeadas y `qtrs`. Esta ingesta no convierte
  `ddate` en fechas de contextos XBRL ni certifica tickers o aliases.
- Se mantienen alternativas de valor dentro de la misma clave redondeada,
  unidades USD/shares, exclusión de segmentos/coreg, tags y taxonomías admitidos,
  y contadores de filas procesadas, incluidas las repetidas. El orden de los
  lotes conserva el efecto de `INSERT OR REPLACE` para SUB duplicado.
- `facts=False` no abre ni exige `num.txt`. La ausencia de columna `segments`
  conserva la interpretación anterior. Fechas NUM inválidas se cuentan como
  inválidas; errores estructurales abortan la importación.

## Archivos, límites y transacción

El lector solo abre el ZIP local. No descarga, extrae archivos, abre SQLite ni
crea directorios. SUB deja de cargarse completo; SUB y NUM usan lotes de 20.000
filas, frente a SUB completo y lotes NUM de 200.000 en la implementación previa.
No hay caché persistente: la siguiente operación vuelve a leer el archivo.

Presupuestos configurables: ZIP de 4 GiB, SUB descomprimido de 256 MiB, NUM de 4 GiB,
25 millones de filas por miembro, DataFrame de 64 MiB por lote y campo UTF-8
de 1 MiB. El caso de uso limita CIK a 10.000 y accesiones seleccionadas a
500.000. Los tamaños declarados del ZIP se comprueban antes de abrir miembros;
los límites de DataFrame/campo se comprueban después de parsear cada lote,
antes de publicar sus filas. No representan un límite duro de RSS del parser.
Un miembro repetido del ZIP se rechaza como ambiguo. Exceder presupuestos
produce error, sin truncar ni importar evidencia parcial.

La importación completa usa una transacción `BEGIN IMMEDIATE`: esquema,
migración del NUM antiguo, SUB y NUM se confirman juntos o se revierten juntos.
Un fallo puede dejar un fichero SQLite vacío, pero no tablas ni filas parciales.
El ZIP y el miembro SUB se abren antes de SQLite; su ausencia o ambigüedad no
crea base de datos. No se recalcula el hash completo del ZIP al importar:
el registro de descarga conserva esa responsabilidad y el argumento URL
mantiene su contrato previo.

`sec_history.SCHEMA` conserva exactamente el texto público anterior y
`date8` delega en dominio. `ensure_schema(conn)` conserva su comportamiento
explícito de compatibilidad: confirma trabajo pendiente e inicializa/migra el
esquema. El importador nuevo usa el inicializador transaccional, sin
`executescript`, commits intermedios ni conexiones globales.

## Pruebas y medición

La fixture `sec_bulk_import_migration.json` captura esquema e implementación
previos. Dieciocho pruebas nuevas comparan contadores y filas exactas con
lotes de 1, 2 y 20.000 filas, reimportación, enmiendas, duplicados, alternativas,
fechas, unidades, ausencias y fachada. Verifican también límites, ZIP ambiguo,
ausencia de descargas y reversión del esquema antiguo con sus datos previos.
Todas usan rutas temporales. Pasan 87 pruebas dirigidas de estos flujos y
arquitectura. Suite completa: 1.826 pruebas correctas y nueve warnings
preexistentes. Tipos sin nuevos diagnósticos; los tres motores CI y los 18
motores/configuraciones publicados conservan sus hashes. Ruff pasa en los
601 archivos Python de código, tests y scripts; `ruff check .` sigue detectando
errores en copias temporales de pytest del workspace, que no se alteran.
`git diff --check` correcto. Las 18 pruebas finales pasan tras añadir el límite
del archivo ZIP completo.

Medición: `.venv/Scripts/python.exe scripts/measure_f7_sec_bulk.py`.
Windows/Python 3.13, ZIP sintético con 5.000 filas SUB, 100.000 NUM y 50 CIK
seleccionados de 500 disponibles. Cuatro ejecuciones por variante, concurrentes
con tests y con `tracemalloc`; memoria Python, no RSS. Contadores y filas finales
exactamente iguales: 500 submissions, 10.000 hechos procesados, 3.500 hechos
distintos. Incluye conexiones/lecturas finales de comprobación.

| Variante | Primera ejecución (s) | Mediana posterior (s) | Pico Python (MiB) |
| --- | --- | --- | --- |
| Implementación capturada | 4,6209 | 4,4152 | 4,1280 |
| Lectura por lotes con presupuestos | 14,9524 | 15,0581 | 2,6364 |

El menor pico medido tiene un coste de CPU significativo al comprobar tamaños
y campos de todos los lotes bajo instrumentación. No se presenta esta
extracción estructural como aceleración; tampoco se extrapola el pico a archivos
reales o RSS. Ambas variantes usan dos conexiones y dos SELECT por ejecución
incluyendo la comprobación final.

## Pendiente

Quedan la selección/coordinación de descargas y su transporte de compatibilidad,
el escaneo e interpretación de covers XBRL de identidad, la recuperación de
contextos XBRL originales, la selección de CIK y los checkpoints de ingesta
legacy. También el agregado small/mid, las lecturas
generales de `storage` y `historical_pit.accredited_periods`. No se declara
completada toda la ingesta histórica, F7 ni #60.
