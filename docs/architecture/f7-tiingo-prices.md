# F7.4: Tiingo, snapshots y checkpoints explícitos

La política de ventanas, listado actual por ticker, elegibilidad, interpretación
de filas, recuento de observaciones nuevas y metadatos vive en dominio. Conserva
las tres ventanas y sus identificadores: `2010-2015`, `2016-2025` y `smallmid`.
Mantiene la distinción entre fechas solicitadas y fin exclusivo de importación;
los datos de una ventana no se añaden a la fuente de otra. Los cierres negociados
y ajustados, dividendos y splits no acreditan por sí solos identidad del emisor.

La aplicación comparte descarga e importación entre la fachada y los caminos
actuales. Recibe fuente, caché, archivo histórico, checkpoints, fábrica de
intentos, espera y progreso. No conoce SQLite, rutas ni configuración global.
Conserva doce intentos, espera de 300 s ante pérdida de red, 900 s ante 429
salvo el último intento, ritmo de 80 s, omisión de archivos existentes y parada
reanudable por cupo persistente o respuesta 200 con un objeto de error.
Si hubo un 429 y después solo fallos de red, conserva ese último estado HTTP,
como la implementación anterior. Un JSON que no sea lista no se guarda.

## Composición y efectos

`gabi_cli/sources/bootstrap.py` compone los mismos casos de uso para
`gabi_cli research tiingo-prices` y el worker F4. La entrada de investigación
admite `--fetch`, `--import-cached`, `--window`, `--cache` y `--db`.
El worker y `gabi_cli periodic` inyectan los callbacks de la ventana small/mid
en el puente periódico; no pasan por la descarga/importación plana ni cambian
configuración por operación. La composición no abre conexiones ni lee claves.
Sin acciones, el CLI no descarga, lee claves, abre SQLite ni crea archivos.
Un hit de caché de descarga tampoco necesita clave ni métricas nuevas.

Las descargas siguen siendo jobs persistentes al ejecutarse desde el programador;
el CLI de investigación es una acción explícita según ADR 0002. No se añade
descarga en GET. El resto de las operaciones periódicas y el cierre de recogida
de small/mid conservan sus puentes y siguen pendientes de migración.

La fuente HTTP consume bloques de 64 KB, cierra respuestas y conserva URL,
cabeceras y timeout de 60 s. La clave solo viaja en Authorization y se carga
por operación con prioridad de `TIINGO_API_KEY` sobre el archivo local; su
lectura se limita a 4 KB. Los errores de red conservan solo su tipo.
El snapshot conserva los bytes recibidos, sin reserializar JSON, y se publica
por reemplazo atómico con limpieza del temporal si falla.

## Integridad, límites e invalidación

La lectura entrega bytes y SHA-256 de la misma lectura. La aplicación compara
primero el hash fijado en metadatos y luego el checkpoint. Si coincide el
checkpoint, no decodifica JSON ni vuelve a importar. Un hash distinto exige
un identificador de fuente nuevo; no se tolera, reesella ni sustituye una
publicación. Los snapshots vacíos también reciben fingerprint y checkpoint.
No hay TTL o descarga implícita; un archivo existente se reutiliza y una
revisión necesita una acción explícita y fuente nueva.

Las importaciones mantienen orden lexicográfico, metadata, contadores, validación
de precios y `INSERT OR IGNORE`. Un rechazo registra fallo y no avanza
fingerprint, watermark exitoso ni last_success; repetir permite revisar el mismo
archivo. El cálculo de nuevas filas mantiene exactamente la regla original,
incluida la exclusión de fechas fuera de ventana.

La política original de eventos/checkpoints se comparte en dominio, incluyendo
redacción de claves, watermark monótono, estados mixtos y saltos. La aplicación
recibe reloj UTC, reloj de pared y CPU. Las conexiones de métricas son cortas;
no se mantienen durante las esperas HTTP. Las consultas de checkpoint no crean
base o esquema. Su JSON y metadata se limitan en SQL antes de devolver contenido
a Python. Eventos y checkpoints se escriben juntos en la transacción.

Límites del camino actual: 1.000 símbolos, 8 MB por respuesta/archivo, 1.000
archivos y 512 MB por importación, 10.000 filas por archivo y dos millones de
filas nuevas por importación. Los archivos ya acreditados se comprueban por hash
sin parsear para contar sus filas. Las fechas existentes se consultan solo por
fuente/símbolo/ventana, con límite de 10.000 filas, sin cargar OHLCV completo.
Checkpoint, evento o metadatos no superan 2 MB. El lector del listado soportado
limita ZIP a 16 MB, CSV a 64 MB y 200.000 filas. Rechaza excesos, no trunca datos.

La fachada `historical_tiingo` conserva constantes, WINDOWS mutable, listado,
elegibilidad, helpers y argumentos para auditorías y small/mid pendientes. Sus
pequeños adaptadores de compatibilidad conservan I/O antiguo; interpretación y
coordinación comparten implementación. `sync_state` delega la política, pero sus
otros lectores/reintentos y helpers siguen pendientes. Quedan 76 módulos planos;
esta entrega no declara completo el núcleo ni F7. Los 18 motores/configuración
y documentos sellados permanecen intactos.

## Pruebas y medida

44 pruebas nuevas comparan la fuente capturada anterior en namespaces privados,
con archivos, SQLite, claves y relojes temporales. Comprueban filas, JSON,
metadatos, bytes, hashes, eventos y checkpoints completos para las tres ventanas,
primera importación y repetición. Incluyen cupos, pérdida de red, estado HTTP
previo, integridad, ausencias, límites, reemplazo fallido, elegibilidad, lecturas
sin escritura y recorrido del worker con descarga/importación legacy prohibidas.
La selección ampliada pasa 176 pruebas de archivo, sincronización incremental,
periodicidad, jobs, WIKI, small/mid y política/auditoría de precios.

`python scripts/measure_f7_tiingo_prices.py` compara importación completa y
repetición con checkpoint. Usa 10 archivos, 22.180 filas diarias sintéticas,
3.371.360 bytes, una primera medida y tres repeticiones; cero descargas.
Compara todas las filas SQL, metadatos, eventos y checkpoints. Los relojes de
eventos se fijan iguales para probar equivalencia; el cronómetro de medida es
real e independiente. La compilación de referencia queda fuera del tramo medido.
Se instrumentan conexiones y SELECT, incluidas preparaciones sobre tablas aún
ausentes, que no crean esquemas. La primera medida no asegura caché fría del
sistema operativo; el pico es de asignaciones Python, no RSS.

| Flujo/ruta | Primera medida (s) | Mediana (s) | Pico Python (MiB) | Conexiones / SELECT |
| --- | ---: | ---: | ---: | ---: |
| Primera importación, original | 4,1943 | 4,4668 | 3,3347 | 52 / 31 |
| Primera importación, migrada | 3,8098 | 3,6946 | 3,6205 | 31 / 31 |
| Checkpoint, original | 0,0492 | 0,0516 | 0,3454 | 12 / 11 |
| Checkpoint, migrada | 0,0656 | 0,0681 | 0,3473 | 11 / 11 |

La primera importación reduce tiempo/conexiones en esta fixture y usa más
memoria Python; la repetición sigue algo más lenta, con pico similar. No se
declara una mejora general ni se extrapola al archivo real. Doce SELECT de la
primera importación migrada encuentran tablas aún ausentes y devuelven ausencia
sin inicializar esquema; están incluidos en el recuento.
