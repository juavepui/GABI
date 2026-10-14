# Yahoo Finance detrás de un proveedor (F7.18)

Continúa [F7.17](f7-http-providers.md) con [ADR 0004](../adr/0004-legacy-provider-delegation.md).
`infrastructure/providers/yahoo.py` es ahora el único módulo de producción que
importa `yfinance`, salvo `smallmid_test`, que reproduce un resultado publicado
y no se toca. Expone `download`, `ticker`, `splits`, `history` y
`use_timezone_cache`.

| Consumidor | Antes | Ahora |
| --- | --- | --- |
| `data_fetch` (precios por lotes, splits, fundamentales) | `yf.download`, `yf.Ticker` | `yahoo.download`, `yahoo.splits`, `yahoo.ticker` |
| `price_sync` | `data_fetch.yf.download` | `yahoo.download` |
| `history_refresh` | `yf.Ticker(...).history`, `yf.set_tz_cache_location` | `yahoo.history`, `yahoo.use_timezone_cache` |
| Puentes `earnings`, `estimates`, `historical_backfill` | `import yfinance` | el mismo proveedor |

Inventario: `data_fetch` y `history_refresh` pierden `yfinance`; `price_sync`
pierde `gabi.data_fetch.yf`.

## Contrato

Mismos argumentos (`period`, `start/end`, `interval`, `group_by`, `threads`,
`auto_adjust`, `progress`), símbolos normalizados, resultados y excepciones.
`yfinance` gestiona su propio HTTP y tamaño de respuesta, así que no se añade
presupuesto de bytes. El proveedor resuelve los atributos de `yfinance` en cada
llamada; los tests y `scripts/benchmark_incremental_sync.py` sustituyen
`yfinance.download`/`Ticker` en lugar de `data_fetch.yf`/`history_refresh.yf`.
`use_timezone_cache` mantiene el ajuste de proceso que `yfinance` impone y solo
se llama en acciones explícitas de refresco.

## Validación

`fixtures/yahoo_provider_migration.json` captura `data_fetch.py` de
`c324aabadf3c7b517129f5cd55ffff880921d865`. `test_yahoo_provider_migration.py`
compara con un `yfinance` simulado las llamadas emitidas y los resultados de
splits, fundamentales (con y sin datos) y precios por lotes (con un ticker
fallido), y que el proveedor resuelve `yfinance` en tiempo de llamada. Dos
mutaciones deliberadas (símbolo de splits y opciones de descarga) hacen fallar
cuatro pruebas. Validación del 2026-10-13: suite Python completa de 1.984 pruebas
correcta. Sin tabla de tiempos: solo cambia el módulo que hace la llamada.
