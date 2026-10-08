# F7.8: coordinación y exportación de auditorías históricas

Continúa [F7.7](f7-historical-composition-writes.md), sin modificar estrategias,
periodos publicados ni motores sellados.

## Flujos migrados

`application/research/historical_composition.py` coordina la composición por
fecha, resolución de identidad, comparación de fuentes e importación del CSV
fijado. El dominio conserva las fronteras de cobertura, correcciones WLP/ANTM,
orden y diferencias entre fuentes. `HistoricalCompositionFiles` verifica el
SHA-256 antes de importar y limita CSV/manifiesto. La consulta de composición
no calcula hashes ni importa archivos.

`application/research/historical_price_audit.py` recibe lector, composición,
calendario, fuentes, nominaciones y evidencia de emisor. Comparte auditoría,
promoción, eventos terminales, sucesiones y ejecución/exportación explícita.
Los cálculos de cobertura, ajustes y evidencia de emisor están en dominio.
La fachada conserva argumentos y salidas; la base indicada por `--db` se usa
también para composición e identidad. Antes esas lecturas utilizaban la base
global aunque los precios se leyeran de otra base.

`application/research/historical_identity_audit.py` construye intervalos
retrospectivos y cobertura trimestral con entradas explícitas. El dominio
conserva candidatos, reciclaje, contradicciones, nominaciones, nombres y
proveniencia; la infraestructura limita las lecturas SQL y filtra pruebas
por la ventana de evidencia antes de decodificarlas. No ejecuta `ensure_schema`
al consultar. Los lectores de nombres y vida del emisor se inyectan; se consultan
vidas solo de candidatos que coinciden con un intervalo de membresía.

`HistoricalAuditFiles` publica CSV/JSON mediante temporal y sustitución de
cada archivo completo. Conserva columnas, ausencias, codificación, serialización
de referencias y saltos de línea de la plataforma. El par CSV/JSON no constituye
una transacción conjunta. Una sustitución fallida conserva el archivo anterior
y elimina el temporal.

`SqliteTickerPrices` sirve el respaldo operativo de `identity.backtest_prices`. Lee los
tickers por lotes de 200, procesa un símbolo cada vez y conserva el contrato
de frames vacíos. Una base ausente no se crea; una base antigua sin `adj_close`
devuelve esa columna ausente de valores sin alterar tablas. La atribución
histórica estricta sigue sin usar este respaldo, salvo el benchmark previsto.

## Límites, caché y efectos

Cada operación abre conexiones de solo lectura con `query_only` y una
transacción de lectura. Las auditorías de precios admiten 25.000 filas y
16 MiB por consulta, campos de 1 MiB y una LRU de 32 MiB por ejecución. Las
referencias al miembro actual se liberan al pasar al siguiente; la LRU y su
snapshot desaparecen al cerrar la operación, por lo que otra ejecución observa
cambios locales. Los splits se consultan por símbolo.

La auditoría de identidad admite 100.000 filas y 32 MiB por conjunto consultado,
con campos de 1 MiB. No mantiene caché. El respaldo por ticker limita una
operación a 1.000 símbolos, 250.000 filas totales, 25.000 por símbolo, 64 MiB
y campos de 16 KiB. Superar un límite produce un error explícito; no trunca
series ni devuelve una cobertura parcial. Estos límites pueden rechazar
archivos operativos mayores que el presupuesto, que antes se cargaban enteros.

Consultar no descarga, acredita ni exporta. Las acciones del runner activan
escritura/descarga de documentos únicamente mediante sus opciones explícitas.
La promoción conserva la sustitución del productor y las transacciones por
intervalo; no se presenta como transacción global de la auditoría.

## Evidencia y medición

`fixtures/historical_runners_migration.json` captura las seis implementaciones
anteriores. Doce pruebas comparan runners de varias fechas, cobertura de
identidad, intervalos, comparación/importación fijada, promoción con ventanas
solapadas, registros persistidos y bytes exportados. Comprueban también
ausencia de red/escritura, base explícita, límites, invalidación de caché y
fallo de publicación. Los datos y destinos son temporales.

Medición reproducible:
`.venv/Scripts/python.exe scripts/measure_f7_historical_runners.py`.
Windows/Python 3.13; 20 símbolos sintéticos, 2.087 filas por símbolo y dos
fechas de auditoría. Cuatro ejecuciones por variante; paridad exacta de frames
y resúmenes. Concurrente con tests, sin datos reales, descargas ni holdouts.

Validación: suite completa de 1.783 pruebas correcta; 148 comprobaciones
finales de runners, identidad, composición, precios y arquitectura, y 47 de
paridad/escritores/almacenamiento tras la lectura incremental. Arquitectura
backend sin crecimiento del baseline, frontend y sus nueve pruebas correctos;
mypy conserva solo los 25 diagnósticos históricos exactos de motores sellados.
Verificados los tres motores CI y los 18 motores/configuraciones publicados.
Ruff comprueba los 588 archivos Python de código, tests y scripts versionados
o nuevos. `ruff check .` sigue encontrando 132 errores en copias/fixtures de
directorios pytest temporales antiguos y rutas sin acceso; esos archivos no
se modifican para limpiar el resultado. `git diff --check` correcto.

| Flujo | Primera ejecución anterior → nueva (s) | Mediana posterior (s) | Pico Python (MiB) | Conexiones | SELECT | Filas entregadas |
| --- | --- | --- | --- | --- | --- | --- |
| Auditoría de precios | 4,3116 → 6,3027 | 4,4363 → 6,0757 | 3,7334 → 3,2761 | 1 → 1 | 125 → 123 | 41.116 → 41.120 |
| Respaldo por ticker | 1,2920 → 4,2141 | 1,2285 → 4,3399 | 3,1181 → 3,0525 | 20 → 1 | 20 → 2 | 41.740 → 41.752 |

La reducción de conexiones no implica menor latencia: comprobar límites fila
a fila cuesta tiempo en esta fixture. La entrega por símbolo evita el pico
intermedio de 20,14 MiB observado en la primera implementación por lotes.
Los picos son asignaciones Python, no RSS. Las filas adicionales corresponden
al inventario de tablas y columnas. El lector anterior del runner se cierra
expresamente en la medición para liberar el archivo temporal en Windows.

## Compatibilidad que permanece

Los lectores de frames/submissions y nombres, y sus cachés globales,
se migran en [F7.9](f7-historical-issuer-files.md). Siguen pendientes los
adaptadores de descarga de `historical_issuer_evidence` y las acciones de
ingesta/escaneo de `historical_identity_audit`.
Las lecturas generales `storage.get_prices/get_prices_multi`, usadas también
por Mercado y por historiales completos, conservan su compatibilidad pendiente;
no se les aplica el presupuesto menor del respaldo de backtests.
La fachada los entrega como dependencias explícitas a los nuevos casos de uso;
estos no importan módulos planos. Tampoco se retira el contexto de compatibilidad
de `historical_pit.accredited_periods`. No se declara migrado todo `historical_*`
ni resuelta la evidencia pendiente de #60.
