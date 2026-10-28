# Lectores EDGAR por fecha de presentación (F7.6)

`domain/market/sec_reads.py` interpreta hechos suministrados: selección de
versiones, valor conocido por fecha y reconstrucción de companyfacts.
`application/market/sec_reads.py` comparte estas operaciones mediante un puerto
de lectura específico y reutiliza `sec_facts.compute_edgar_metrics`, sin copiar
fórmulas. La fachada EDGAR delega en estos casos de uso y conserva su interfaz,
incluida la alineación fiscal explícita de los consumidores antiguos.

## Contratos conservados

- Por CIK se conservan todas las versiones con `filed_date <= corte` y
  `end_date <= corte`, formas 10-K/10-Q y sus amendments, accession y URL de
  procedencia. El orden publicado es fecha de presentación, fin de período,
  accession y tag. No se resuelve ni acredita un ticker histórico.
- Para métricas y valores históricos, el contrato anterior corta únicamente
  por fecha de presentación; no se añade un filtro de forma o fin de período.
  La reconstrucción preserva unidades, ausencias y revisiones. El cálculo de
  métricas conserva los criterios financieros ya migrados en `sec_facts`.
- El valor escalar mantiene la selección por fecha de presentación y fin de
  período sobre los tags solicitados. No se introduce una nueva prioridad
  entre tags ni se interpreta como valor anual un hecho trimestral.
- Los hechos atribuidos se ordenan por símbolo y clave. Una duplicación entre
  aliases conserva la primera atribución para la clave XBRL antes del corte
  temporal. Adelantar el filtro podría rescatar otra versión y cambiar el
  resultado histórico; esta frontera tiene una prueba específica.
- La última fecha de filing por ticker mantiene `MAX(filed_date)`, corte
  opcional y ausencia de claves sin datos; el nuevo lector procesa por lotes.

## Flujo local y límites

`SqliteSecReads` recibe ruta y presupuestos. Cada operación abre su propia
conexión `mode=ro` y `query_only`, sin crear DB, directorios o esquemas, ni
contactar fuentes. La consulta por ticker filtra fecha, tags y unidad en SQL.
La consulta por CIK filtra fechas antes de decodificar sus versiones; la de
métricas atribuidas conserva el orden de deduplicación y lectura del emisor.

Los límites predeterminados son 250.000 filas, 64 MiB acumulados y 16 KiB por
fila; SQLite limita además la materialización de valores. Los JSON grandes
se detectan antes de decodificarlos. Un exceso falla sin truncar resultados.
La consulta en lote admite 1.000 símbolos y lotes de 200; el filtro de hechos
por ticker admite hasta 200 tags. No se añade caché de resultados, por lo que
una revisión del emisor se observa en la siguiente conexión.

El bootstrap de investigación compone el lector con Settings en:

```powershell
uv run --project backend python -m gabi_cli research sec-facts --cik 1 --as-of 2020-12-31
```

`--tag Revenues` puede repetirse para filtrar las versiones mostradas. Las
métricas y acciones se calculan con todos los conceptos disponibles del
emisor. El comando devuelve JSON finito con CIK, corte, versiones, métricas y
acciones, sin escribir archivos ni lanzar descargas. Versiones y métricas del
comando proceden de un único SELECT del emisor; un commit concurrente no mezcla
revisiones entre ambas salidas. Una caché ausente devuelve
hechos vacíos y métricas ausentes.

La fachada EDGAR usa ahora el mismo `SqliteSecReads`: retira `_FactReader` y sus
consultas SQL de compatibilidad para hechos crudos, versiones por CIK, valores,
acciones, métricas históricas y últimas fechas de filing. La ruta de compatibilidad
se captura por operación; no se modifica configuración global ni se registra un
lector global. Conserva el callback fiscal explícito del cálculo EDGAR.

Los consumidores del ranking histórico, persistencia de calidad, asignación de
capital, Portfolio Lab y motores congelados conservan sus interfaces y reciben
estas lecturas acotadas sin inicializar tablas. Una base o tabla ausente devuelve
ausencias; ya no se crea para consultar. Los presupuestos del lector también se
aplican a la fachada y fallan sin truncar. Cada conexión observa las revisiones
posteriores; no se añade caché. [ADR 0003](../adr/0003-legacy-storage-delegation.md)
documenta la delegación de SQL desde fachadas existentes hacia almacenamiento,
con pruebas de frontera y sin ampliar el inventario de excepciones.

El [núcleo de identidad y su guard de últimas fechas atribuidas](f7-issuer-identity.md)
ya usan lectores compartidos. Las lecturas actuales de métricas cacheadas
también (sección siguiente). Siguen pendientes otros flujos históricos y las
escrituras de `edgar_metrics`. No se presenta este bloque como eliminación completa de `edgar.py`
ni como consulta libre de efectos de todo el ranking. No cambian motores ni
configuración congelados.

## Métricas cacheadas actuales

`get_edgar_metrics`, `get_edgar_fetched_at` y `get_symbols_with_facts` delegan
en `cached_metrics`, `fetched_at` y `symbols_with_facts` de
`application/market/sec_reads.py`, sobre `SqliteSecReads`. Ya no ejecutan
`CREATE TABLE` al consultar ni abren la conexión legacy: base o tabla ausente
devuelve `{}`/`set()` sin crear nada. Se conservan las columnas y claves del
resultado, la deduplicación de símbolos repetidos, la ausencia de símbolos sin
fila y `None` cuando `fetched_at` no es una fecha ISO.

Los símbolos se consultan en lotes de 200 dentro de una única transacción de
lectura, de modo que todos los lotes observan la misma revisión. Ambas tablas
tienen como máximo una fila por símbolo y lote (clave primaria o `DISTINCT`),
así que la materialización queda acotada por la entrada; cada fila sigue
limitada a 16 KiB y un exceso falla sin truncar. No se añade un tope de
símbolos para no cambiar el contrato del ranking y la calidad de datos, que
consultan el universo completo. No hay caché: la siguiente consulta observa
la siguiente sincronización. Las escrituras (`upsert_edgar_metrics`) siguen
en la fachada.

Referencia capturada `c324aabadf3c7b517129f5cd55ffff880921d865` en
`fixtures/sec_cached_metrics_migration.json`. `test_sec_cached_metrics_migration.py`
compara caso de uso y fachada con las funciones originales (vacío, ausente,
repetidos, fecha inválida, 452 símbolos), y prueba base/tabla ausente sin
creación, tres lotes por consulta, cero escrituras, bytes de la base intactos,
prohibición de la conexión legacy y límite por fila.
Validación del 2026-10-11: suite Python completa de 1.853 pruebas correcta.

Medida reproducible: `.venv/Scripts/python.exe scripts/measure_f7_sec_cached_metrics.py`.
Windows/Python 3.13, 500 símbolos y 20.000 hechos sintéticos, ejecución fría y
tres repeticiones; paridad exacta y cero descargas.

| Consulta | Frío anterior → nuevo (s) | Mediana caliente (s) | Pico Python (MiB) | SELECT | Sentencias de esquema |
| --- | --- | --- | --- | --- | --- |
| Métricas cacheadas | 0,0068 → 0,0093 | 0,0022 → 0,0032 | 0,3968 → 0,3392 | 1 → 4 | 1 → 0 |
| Fecha de descarga | 0,0031 → 0,0049 | 0,0013 → 0,0021 | 0,1201 → 0,1009 | 1 → 4 | 1 → 0 |
| Símbolos con hechos | 0,0033 → 0,0051 | 0,0026 → 0,0034 | 0,0888 → 0,0647 | 1 → 4 | 2 → 0 |

Los SELECT nuevos son el inventario de tablas y tres lotes. Las consultas son
entre uno y dos milisegundos más lentas en esta fixture; el cambio elimina
escrituras de esquema en lecturas y acota los lotes, no promete más velocidad.

## Lectores por símbolo y aliases del emisor (#201)

La sincronización SEC escribe en `edgar_facts`, bajo el símbolo actual, solo
los hechos que la entidad no conocía. Si el historial se guardó antes con otro
alias (ticker anterior o clave histórica `CIK…`), leer `edgar_facts` por
símbolo devuelve medio historial. `entity_observations` conserva el historial
completo de la entidad. Clasificación de los lectores por símbolo:

| Lector | Consumidores | Clase | Lectura |
| --- | --- | --- | --- |
| `SqliteSignals.filing_facts` | comparación de presentaciones 10-K/10-Q de señales | Mercado | Por entidad del CIK guardado en `edgar_metrics`; sin CIK o sin observaciones, por símbolo |
| `SqliteSecReads.symbols_with_facts` (`edgar.get_symbols_with_facts`) | selección SEC de `ensure_edgar_data`, calidad de los datos | Ingesta y consulta | Símbolo con filas propias o cuya entidad tiene hechos |
| `SqliteSecSelection.current` | selección SEC del CLI de fuentes | Ingesta | Igual que el anterior |
| `SqliteSecReads.issuer_facts` | checklist y múltiplos sectoriales | Mercado | Por entidad desde #170 |
| `SqliteSecReads.last_filed` en el checklist | clave de la caché de múltiplos sectoriales | Mercado | Sin cambio: una presentación nueva siempre se escribe bajo el símbolo actual y cambia la clave |
| `facts`/`stored_facts`/`metrics_as_of`/`concept_value` sin `entity_id` (`edgar.get_edgar_facts`, `_facts_dict_from_stored`, `compute_edgar_metrics_as_of`, `get_shares_outstanding_as_of`) | `screener_asof` → ranking histórico, `full_universe_audit`, `overfitting_audit`, `r3_experiment` y demás investigación | Composite histórico y congelados | Sin cambio. Reciben `entity_id` cuando la identidad acreditada lo resuelve; leer por entidad en el resto exige versión nueva con validación separada |
| `SqliteSecReads.last_filed` (`edgar.get_last_filed_dates`) | guard de reciclaje de Portfolio Lab | Investigación | Sin cambio |
| `SqliteIdentityReads.filing_dates` | `identity.last_filings` → backtests | Composite histórico | Ya por entidad para propietarios acreditados; por ticker solo sin propietario |
| `historical_data_audit` (`_ticker_inputs`, `year_counts`) y `historical_backfill` | auditorías históricas publicadas | Auditoría | Sin cambio: reproducen el flujo operativo que auditan |

Las tres lecturas corregidas no cambian el Composite, el ranking ni los hashes
congelados. La de señales conserva columnas, orden (`end_date`, `filed_date`),
límite de 50.000 hechos y CIK devuelto; deduplica por clave XBRL como el
lector por entidad y controla el tamaño del JSON antes de decodificarlo. En la
cobertura, un símbolo sin filas propias cuesta una consulta por lote a
`edgar_metrics` y otra a `entity_observations` (índice por entidad y dataset);
sin tabla de entidades se conservan las consultas anteriores. Antes, un símbolo
con todo su historial bajo otro alias se marcaba sin hechos y se volvía a
descargar en cada actualización.

`test_sec_alias_readers.py` cubre historial repartido entre alias, símbolo sin
CIK, CIK sin hechos y JSON sobredimensionado. Pendiente, con validación
separada: medir cuánto cambiaría el ranking si el Composite leyera por entidad
y, como alternativa de raíz, reasignar al símbolo actual las filas de otros
alias durante la sincronización (escritura explícita con migración y auditoría).

## Validación y medida

La referencia capturada es `174f944210fe0a07d0186f8d60bbe05822c9c452`.
`test_sec_reads_migration.py` compara DataFrames, companyfacts, métricas,
valores y fechas con las funciones originales en SQLite temporal. Cubre cinco
cortes, ausencia de datos, tags, USD/shares, revisiones, amendments, aliases
duplicados, otro CIK y un período posterior al corte con filing anterior.
Comprueba límites, ausencia de red/escrituras y composición del comando sin
lectores legacy.

La migración de la fachada añade comparación directa con esa referencia,
política fiscal activada/desactivada, persistencia de calidad y almacenamiento
ausente, prohibiendo conexiones SQL legacy. Validación del 2026-10-08:
162 pruebas de lectores, arquitectura, EDGAR, identidad, ranking histórico,
calidad, asignación de capital, sincronización incremental y Portfolio Lab;
guardas backend/frontend, nueve pruebas de arquitectura frontend, lint de
Python versionado, tipos y hashes congelados correctos.

Medida reproducible:
`.venv/Scripts/python.exe scripts/measure_f7_sec_reads.py`.
Windows/Python 3.13, un emisor, 3.000 hechos en cada tabla fuente, corte
2020-12-31, ejecución fría y tres repeticiones adicionales. Cero descargas;
paridad exacta de resultados. El pico mide asignaciones Python, no RSS.

| Consulta | Frío anterior → nuevo (s) | Mediana caliente (s) | Pico Python (MiB) | Filas de hechos leídas |
| --- | --- | --- | --- | --- |
| Métricas por ticker | 0,2611 → 0,2050 | 0,2350 → 0,1831 | 2,3109 → 0,8559 | 3.000 → 1.200 |
| Métricas atribuidas | 0,4128 → 0,3980 | 0,3281 → 0,3118 | 5,0695 → 5,2926 | 3.000 → 3.000 |
| Versiones por CIK | 0,0764 → 0,0866 | 0,0774 → 0,0827 | 2,0466 → 2,0470 | 1.200 → 1.200 |

Cada consulta usa una conexión antes y después; los SELECT pasan de uno a dos
por el inventario de tablas (dos filas de metadatos adicionales en esta fixture).
Las métricas por ticker reducen materialización. La consulta de versiones
aumenta tiempo y las métricas atribuidas aumentan asignaciones. Los tiempos
son observaciones de esta fixture, no una mejora general de la ingesta ni
una predicción para datos reales o consultas durante un refresco concurrente.

Repetición del 2026-10-08 con la misma fixture y comprobaciones en paralelo:
paridad exacta y cero descargas. Frío/caliente por ticker: anterior
0,6857/0,3346 s, nuevo 0,3240/0,3138 s; por entidad: anterior
0,5121/0,5116 s, nuevo 0,6506/0,6794 s; versiones: anterior
0,1567/0,1480 s, nuevo 0,1790/0,1839 s. Filas, consultas y picos Python
coinciden con la tabla. No se atribuye una mejora general: las lecturas por
entidad y de versiones fueron más lentas en esta ejecución.
