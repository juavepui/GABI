# Lecturas de la caché operativa de precios y fundamentales (F7.12)

`storage.py` conserva su interfaz, pero sus lecturas ya no abren la conexión
legacy ni ejecutan `CREATE TABLE`/`ALTER TABLE` al consultar. Delegan en
`application/market/cached_data.py`, que recibe un puerto de lectura y convierte
filas en los mismos DataFrames y diccionarios. `SqliteCacheReads`
(`infrastructure/storage/cache_reads.py`) implementa ese puerto con las
primitivas compartidas de `bounded_reads`: `mode=ro`, `query_only` y una
transacción de lectura por operación. La fachada captura `config.DB_PATH` en
cada llamada, como permite [ADR 0003](../adr/0003-legacy-storage-delegation.md).

Funciones migradas: `get_prices`, `get_prices_multi`, `get_price_coverage`,
`get_price_as_of`, `has_verified_price_as_of`, `get_split_factor_since`,
`get_fundamentals`, `get_fundamentals_fetched_at` y `get_recent_update_errors`.
`get_latest_price_date` no tenía consumidores (solo aparece en fixtures
capturadas) y se retira. Las escrituras (`upsert_*`, `record_update_errors`,
`init_db`) y `get_connection` siguen en la fachada.

## Contratos conservados

- Mismas columnas, tipos, índice de fechas y orden de claves. La conversión de
  filas usa `DataFrame.from_records(..., coerce_float=True)`, la misma que
  `read_sql_query`.
- Una base anterior a la columna `adj_close` se lee como ausencia de cierre
  ajustado (`NULL`); ya no se altera la tabla al consultar.
- `fetched_at` no ISO o no textual sigue devolviendo `None`; el parser es común
  con las métricas EDGAR cacheadas.
- El factor de split multiplica los ratios posteriores no nulos; sin splits es 1.0.
- Base o tabla ausente devuelve vacío, `None`, `False` o 1.0 según la función,
  sin crear el directorio, la base ni el esquema.

## Límites e invalidación

Los símbolos se consultan en lotes de 500 dentro de una única transacción. Los
precios multi-símbolo admiten 8.000.000 filas acumuladas y 1 GiB por lote: por
encima del volumen documentado de 5.302.967 filas en `prices`
([auditoría 2010–2015](../historical-prices-2010-2015.md)), para que una fachada
de universo completo falle en lugar de truncar. Una serie o lista de splits
admite 50.000 filas y cada campo 4 MiB. Un exceso lanza `ValueError` sin
devolver resultados parciales. No hay caché: cada llamada observa la última
revisión confirmada.

Los precios multi-símbolo se leen en el orden de la clave primaria
(`symbol,date`). El resultado agrupado por símbolo es idéntico al de
`ORDER BY date`, y evita el ordenamiento top-N que SQLite usa con `LIMIT`
(medido: 14,6 s frente a 1,9 s para 625.000 filas).

## Validación y medida

Referencia capturada `c324aabadf3c7b517129f5cd55ffff880921d865` en
`fixtures/storage_cache_reads_migration.json`.
`test_storage_cache_reads_migration.py` compara las nueve funciones con las
originales en 3, 30 y 1.100 símbolos, con y sin columna `adj_close`, nulos,
splits nulos, `fetched_at` inválido, filtros de errores y símbolos repetidos o
ausentes. Comprueba base/tabla ausente sin creación, tres lotes para 1.100
símbolos, cero sentencias de escritura, bytes intactos, prohibición de la
conexión legacy y fallo sin truncar por filas, bytes, campo y lote.

Medida reproducible: `.venv/Scripts/python.exe scripts/measure_f7_storage_reads.py`.
Windows/Python 3.13, 500 símbolos y 625.000 filas de precios sintéticas; frío,
mediana de tres repeticiones y una ejecución aparte con `tracemalloc` para el pico.
Paridad exacta y cero descargas.

| Consulta | Frío anterior → nuevo (s) | Mediana caliente (s) | Pico Python (MiB) | SELECT | Esquema |
| --- | --- | --- | --- | --- | --- |
| Precios de un símbolo | 0,0170 → 0,0106 | 0,0104 → 0,0103 | 0,43 → 0,41 | 1 → 2 | 5 → 0 |
| Precios del universo | 3,6822 → 3,6517 | 2,8154 → 3,5449 | 305,12 → 296,51 | 1 → 2 | 5 → 0 |
| Cobertura de precios | 0,2563 → 0,2575 | 0,2628 → 0,2660 | 0,15 → 0,16 | 1 → 2 | 5 → 0 |
| Fundamentales | 0,0053 → 0,0074 | 0,0050 → 0,0062 | 0,68 → 0,69 | 1 → 2 | 5 → 0 |
| Factor de split | 0,0011 → 0,0009 | 0,0008 → 0,0009 | 0,00 → 0,00 | 1 → 2 | 5 → 0 |

El SELECT adicional es el inventario de tablas. La lectura de universo es
alrededor de un 25 % más lenta en caliente por la comprobación de presupuesto
fila a fila; a cambio deja de escribir esquema en cada lectura. Son tiempos de
esta fixture, no una predicción para la base real.
