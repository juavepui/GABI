# F7.4: mapa SEC y resoluciones ticker/CIK

Entrega para #90/#91. `application/market/sec_cik.py` comparte el refresco del
mapa vigente y la resolución con caché entre la fachada EDGAR y el worker de
insiders. Recibe caché, fuente, persistencia, intento, checkpoint, reintento,
fingerprint y reloj por parámetros. `gabi_cli/sources/bootstrap.py` conecta los
adaptadores; construir el resolver no lee archivos, abre SQLite ni descarga.

## Compatibilidad y frontera de identidad

`domain/market/sec_cik.py` conserva el orden del proveedor, relleno CIK a diez
dígitos, título y prioridad de la primera coincidencia. Busca el símbolo exacto
y, si falta y contiene punto, su notación con guion. No cambia mayúsculas ni
adivina correspondencias. Una coincidencia vigente se recuerda bajo el símbolo
solicitado; si falta, retorna la resolución que funcionó antes, o `(None, None)`.

Esto es un **mapa actual**, no una prueba de identidad histórica. No acredita
que un ticker reciclado corresponda al mismo emisor en otra fecha. El modo
histórico sigue necesitando sus alias/evidencia y no se convierte en lookup vivo.

La caché conserva siete días de vigencia (`edad < 7 días`); el límite exacto
vence y `force_refresh` descarga explícitamente. Un fallo de fuente registra
el intento y devuelve la caché anterior cuando existe. Sin caché, propaga el
fallo. La respuesta satisfactoria reemplaza el CSV antes de registrar su
fingerprint y evento. Estados `new`/`unchanged`/`revised`, errores y recuperación
conservan los checkpoints/eventos publicados. Se mantiene el pacing/reintento
compartido mediante el puente explícito `source_errors`.

La fachada `edgar` conserva sus nombres públicos y rutas/configuración de
compatibilidad, y delega interpretación/coordinación. El worker recibe el
resolver nuevo junto al adaptador Form 4. El fallback legacy del adaptador
queda para sus consumidores directos existentes; la composición moderna de
insiders no llama al mapa/resolución planos.

## Sucesiones revisadas (#202)

En una reorganización como holding, el fichero de tickers de la SEC pasa el
ticker al registrante nuevo antes de que presente estados anuales, mientras la
predecesora sigue presentando como filial. `domain/market/sec_succession.py`
registra cada caso revisado contra el 8-K12B de la sucesora: CIK sucesora →
CIK predecesora, fecha efectiva y accession. No se infiere nada de nombres ni
de reutilización de tickers; un caso nuevo exige revisar EDGAR y añadir su
entrada con test.

La regla se aplica en `application/market/sec_xbrl.synchronize`, el único
punto que ya descarga las presentaciones del CIK. Si el CIK resuelto es una
sucesora revisada, se leen sus presentaciones. Mientras no incluyan un 10-K,
la sincronización usa la predecesora: hechos, métricas, checkpoint y
`edgar_metrics.cik`. Cuando la sucesora presente su primer 10-K, la siguiente
sincronización pasa a ella sin tocar el CSV ni la tabla de resoluciones, que
siguen reflejando el mapa vigente. La comprobación cuesta una petición a
EDGAR, que se suma al intento del emisor; si falla, se registra como fallo de
la sucesora y no escribe nada. Los lectores por entidad (#170, #201) unen el
historial de los alias de la predecesora.

| Sucesora | Predecesora | Ticker | Efectiva | Evidencia |
| --- | --- | --- | --- | --- |
| 0002115436 ExxonMobil Holdings Corp | 0000034088 Exxon Mobil Corp | XOM | 2026-07-01 | 8-K12B 0001193125-26-291990; 25-NSE de la predecesora el 2026-07-02 |

Inventario del 28-10-2026, en solo lectura sobre la base local: de 621 símbolos
con CIK guardado, 6 tienen un CIK sin 10-K entre sus hechos. Solo XOM es una
sucesión de holding. HONA (CIK 0002089271, 69 hechos) es una escisión de
Honeywell (Form 10-12B): no hereda los estados de la matriz y queda sin
cambios hasta su primer 10-K. APC, EP, LB y STI son tickers históricos que el
mapa actual asigna a otras empresas (ARKO Petroleum, Empire Petroleum,
LandBridge y Solidion Technology), sin hechos guardados; son un caso de
reutilización de tickers, no de sucesión.

## IO acotado e invalidación

- Fuente SEC: User-Agent explícito, timeout 20 s, streaming en bloques de 64 KiB,
  hasta 16 MiB decodificados y 50.000 entradas. No trunca respuestas excesivas.
- CSV: hasta 16 MiB y 50.000 filas. Verifica el tamaño del archivo **abierto**,
  lee tamaño + 1 y detecta cambios durante la lectura. CSV, ceros CIK, títulos,
  orden y ausencias mantienen los bytes/valores históricos.
- Escritura del CSV mediante archivo temporal único y reemplazo atómico; un
  fallo del reemplazo conserva los bytes anteriores y limpia su propio temporal.
- Resoluciones SQLite: conexión corta por operación, reloj UTC explícito y
  hasta 16.384 bytes por campo. La lectura filtra por PK y valida tamaños en SQL
  antes de materializar campos. No crea DB/tablas cuando faltan.
- El mapa no usa una caché de cálculo adicional: un refresco reemplaza el CSV,
  cambia su mtime y registra fingerprint de filas. Un fallo conserva el archivo
  anterior, sin renovar su vigencia. Una resolución nueva actualiza su fila y
  fecha; los lectores de mercado conservan invalidación SQLite/WAL.

## Evidencia y medición

`backend/tests/fixtures/sec_cik_migration.json` captura el código anterior a la
extracción, commit `a6a165e23930804649c7b4980ae529ce621f642f`. La referencia no
requiere historia Git en CI. Las 16 pruebas nuevas cubren coincidencia exacta,
clase con punto, símbolos ausentes, fallback, TTL, límite exacto de siete días,
fallo sin caché, límites, reemplazo fallido, lectura sin inicialización y
composición real del worker. Comparan CSV byte a byte, DataFrames y las tablas
completas `cik_resolutions`, `sync_checkpoints` y `sync_events`: primer refresco,
hit, refresco sin cambios, revisiones, fallo con respaldo y recuperación.

108 pruebas pertinentes locales superadas, además de arquitectura, Ruff, tipos,
contrato OpenAPI, motores/configuración congelados y ledger publicado. Solo
datos sintéticos, DB temporales y red simulada; no fuentes reales ni holdouts.

`python scripts/measure_f7_sec_cik.py`: mapa de 5.000 filas, 50 resoluciones
con lectura de respaldo, CSV de 238.908 bytes. Cuatro ejecuciones con directorios
temporales nuevos: primera medición y mediana de las tres posteriores. Relojes
de eventos fijos, duración externa real y `tracemalloc`; cero descargas.

| Flujo | Variante | Primera (s) | Mediana posterior (s) | Pico Python (MiB) | Conexiones | SELECT |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Inicial + resoluciones | Original | 0,7073 | 0,7506 | 4,1170 | 103 | 52 |
| Inicial + resoluciones | Migrada | 0,6678 | 0,6614 | 3,8141 | 101 | 50 |
| Mapa vigente | Original | 0,03546 | 0,03544 | 1,0457 | 0 | 0 |
| Mapa vigente | Migrada | 0,03415 | 0,03457 | 1,2664 | 0 | 0 |
| Forzado + resoluciones | Original | 0,8240 | 0,6548 | 3,7837 | 103 | 52 |
| Forzado + resoluciones | Migrada | 0,7595 | 0,6985 | 3,7828 | 103 | 52 |

Frames, CSV, resoluciones, eventos y checkpoints coinciden en todas las
repeticiones. El refresco forzado migrado resulta más lento en esta medida y
el mapa vigente usa más memoria Python. No se atribuye una mejora general.
El pico mide asignaciones Python, no RSS; la primera medida no acredita caché
fría del sistema operativo. La lectura inicial reservaba innecesariamente el
límite de 16 MiB para un archivo pequeño: la medida final usa tamaño abierto + 1.

## Trabajo pendiente

Se mantienen 76 módulos planos y no se amplía el baseline. Continúan pendientes
la sincronización XBRL y sus consultas/almacenes, identidad histórica, precios,
fuentes y núcleo, además de retirar fachadas cuando desaparezcan sus consumidores.
Los helpers de pacing/reintento/fingerprint permanecen tras `source_errors` hasta
migrar ese flujo común. Los 18 motores/configuración y los documentos sellados
conservan sus bytes; #60 sigue pendiente de evidencia. Esta entrega no completa
los criterios globales de #90/#91.
