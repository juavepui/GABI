# F7.4: archivo de precios WIKI

La interpretación de respuestas, columnas, etiquetas y metadatos WIKI vive en
dominio. La validación original del archivo histórico también está en dominio:
ventana de inicio incluido/fin excluido, normalización de puntos a guiones,
selección de símbolos, fechas, números finitos, precios positivos, volumen no
negativo, coherencia OHLC con tolerancia 0,001 y rechazo de duplicados. El módulo
`historical_archive` delega esta validación; sus demás responsabilidades siguen
pendientes. No se atribuye identidad ni se activan aliases con estos precios.

La aplicación comparte los casos de descarga e importación entre compatibilidad
y CLI. Recibe caché, fuente, almacén, clave, espera y progreso por operación. La
descarga conserva seis intentos, espera de 300 s ante errores de red y 600 s ante
429, omisión de caché existente, pausa de 0,5 s tras éxito, rechazo de paginación,
contadores y mensajes. Solo conserva el tipo de error de red; su URL podría llevar
la clave. La descarga nunca importa precios por sí sola y la importación local no
recibe una fuente de red.

`python -m gabi_cli research wiki-prices --fetch <símbolos> --import-cached`
compone implementaciones explícitas en bootstrap. `--cache` y `--db` permiten
elegir sus destinos; por defecto conserva `history_refresh/nasdaq_wiki` y
`gabi.db` en el directorio de settings. Las acciones son explícitas; sin ninguna
acción no lee claves, crea directorios, abre SQLite ni descarga. Este comando de
investigación sigue ADR 0002; no añade descarga en GET ni tareas HTTP de fondo.
Si se incorpora a la interfaz, deberá ejecutarse como job persistente F4.

## Límites, procedencia e invalidación

El proveedor consume bloques de 64 KB, cierra la respuesta y conserva URL,
parámetros y timeout de 90 s. Limita cada respuesta a 8 MB; no persiste petición,
cabeceras, clave ni metadatos del servidor. El archivo local conserva exactamente
el JSON original de columnas/datos mediante reemplazo atómico. Rechaza nombres
que escapen del directorio, más de 8 MB/5.000 filas por archivo, más de 1.000
archivos o 512 MB totales por importación. El caso de uso limita 1.000 símbolos
por descarga y dos millones de filas por importación. Los excesos se rechazan,
no se truncan. La clave local se limita a 4 KB; la variable de entorno tiene la
misma prioridad que antes. El fichero de símbolos respeta el límite de settings.

El SHA-256 se calcula sobre los mismos bytes UTF-8 que se decodifican, una vez
por importación explícita, incluyendo archivos vacíos. Se conserva el orden
lexicográfico y el identificador `nasdaq-wiki:frozen-2018-03-27`, los cierres
negociados/ajustados, fechas, unidades y metadatos. La validación global conserva
el rechazo de duplicados y los contadores; SQLite mantiene `INSERT OR IGNORE`
idempotente. La conexión pertenece a la operación y se cierra también si falla.

No hay TTL ni refresco implícito: un archivo existente se reutiliza hasta una
acción explícita de mantenimiento. La fuente fijada no sobreescribe precios ya
importados al repetirla. Una revisión de datos debe recibir un identificador nuevo;
borrar la caché no convierte precios previamente importados en una versión nueva.
La limitación por reutilización de ticker y la necesidad de evidencia SEC siguen
vigentes. No se regeneran publicaciones ni se consultan reservas.

`historical_wiki` conserva nombre, constantes y helpers públicos para
`historical_price_audit`, `smallmid_test` y consumidores publicados. Es una
fachada con adaptadores I/O de compatibilidad; comparte interpretación y casos
de uso, pero su ruta antigua de descarga no adquiere los límites del proveedor
nuevo. Estos adaptadores desaparecerán al migrar sus consumidores. El inventario
se poda: salen pandas de WIKI y numpy del archivo histórico; quedan 76 módulos
planos. No se declara terminada F7 ni todo el núcleo de archivo histórico.

## Verificación y medida

La fuente anterior capturada en una fixture se ejecuta en un namespace privado
con archivos, bases y claves temporales. 35 pruebas nuevas comprueban resultados
completos, JSON, SHA-256, filas SQL ordenadas, idempotencia, límites, valores
ausentes/no numéricos, precios inválidos, nombres, fallos de publicación,
reintentos, paginación y composición/cierre del CLI. La selección ampliada de
138 pruebas incluye archivo histórico, auditorías de precios/identidad, política,
small/mid y arquitectura.

Medida reproducible: `python scripts/measure_f7_wiki_prices.py`, 20 archivos
sintéticos con 44.360 observaciones diarias de 2008–2016, 2.575.400 bytes, tres
repeticiones tras la primera medida. Compara la importación completa hasta SQL,
no solo una transformación. Ambas rutas conservan metadatos JSON, hashes,
contadores y todas las filas ordenadas; no descargan y ejecutan cero SELECT
dentro del flujo. La original abre dos conexiones para registro/importación;
la nueva usa una conexión propia de la operación. Los resultados de tiempo y
pico de asignaciones Python observados son:

| Ruta | Primera medida (s) | Mediana caliente (s) | Pico Python (MiB) |
| --- | ---: | ---: | ---: |
| Original | 6,4660 | 7,2805 | 19,1310 |
| Migrada | 5,7670 | 6,1889 | 18,9309 |

Esta fixture muestra menor tiempo y un pico similar; no prueba RSS ni presupuestos
de rendimiento para todo el archivo real. La primera medida no asegura una caché
fría del sistema operativo. La preparación de objetos y la compilación de la
referencia capturada quedan fuera del tramo medido en ambas rutas.
