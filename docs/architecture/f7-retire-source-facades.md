# Retirada de `price_sync`, `macro` e `insider` (F7.25, #90)

Primera entrega para vaciar los pendientes del
[inventario de compatibilidad](compatibility-inventory.md). Las tres fachadas ya solo
componían casos de uso, almacenes y proveedores existentes, y ningún motor congelado,
huella publicada ni `model_version` las lee por nombre. Se retiran sin cambiar
fórmulas, unidades ni el orden de las escrituras:

| Consumidor | Antes | Ahora |
| --- | --- | --- |
| `data_fetch.ensure_universe_data` | `price_sync.run` | `data_fetch.sync_prices`: el mismo cableado de `application/market/price_sync.run` (almacén sobre `SqliteCacheReads`/`SqliteCacheWrites`, `identity.resolve`, `sync_state`, `yahoo.download`) |
| `data_quality` | `insider.get_insider_fetched_at`, `macro.get_all_fetched_at`/`get_series_history`/`SERIES` | `SqliteInsiders.fetched_at`, `SqliteFred.fetched_at_all`/`history`, `domain.market.fred.SERIES`, con `config.DB_PATH` leído en cada operación |
| `history_refresh` | `macro.fetch_series(..., limit=10000)` y `macro.upsert_series` | `FredSource().fetch(..., 10000, require_complete=False)` y `SqliteFred.upsert` |
| `LegacyPeriodicOperations.refresh_macro` sin `macro_sync` | `macro.ensure_macro_data` | `infrastructure/legacy/fred.fred_operation(data_dir)` |
| `sync_company(..., "insiders")` sin `insider_sync` | `insider.ensure_insider_data` | `infrastructure/legacy/insiders.insider_operation(data_dir)` |

`fred_operation` e `insider_operation` son la composición que ya usaba el bootstrap
del CLI (`build_fred_operation` y `build_executor` delegan ahora en ellas), así que el
worker y los llamadores de compatibilidad comparten un único camino. Viven en
`infrastructure/legacy` porque reintentan con el marcapasos único de `sync_state`
(F7.15) y, sin resolutor explícito, insiders usa el mapa CIK de `edgar`.

La clave FRED del respaldo se lee con `providers.fred.fred_key(data_dir)` en lugar de
`config.load_fred_key()`; ambos leen `fred_api_key.txt` del mismo directorio, que
`LegacyPeriodicOperations` ya exige que coincida con `config.DATA_DIR`.
El respaldo de insiders pide los envíos con `SecForm4Documents`, como el worker, en
lugar de `edgar.fetch_submissions`: misma URL y User-Agent; solo cambia el texto del
error cuando SEC devuelve 404.

`data_fetch` sigue pendiente: `sync_prices` se moverá con el resto de la descarga
operativa al caso de uso compartido con el worker.

## Pruebas y medida

Las pruebas de paridad capturada (`test_price_sync_migration`,
`test_operational_sources_migration`, `test_http_providers_migration`,
`test_fred_migration`, `test_legacy_facades_migration`,
`test_ranking_quality_migration`) comparan ahora la referencia capturada con los
sustitutos; `test_ranking_quality_migration` da al `data_quality` capturado lectores
con la interfaz retirada sobre los mismos almacenes. `test_macro`, `test_insider` y
`test_data_quality` usan los almacenes, el dominio y `fred_operation` directamente.
`test_periodic_without_callback_uses_the_same_operation` y
`test_compatibility_operation_reuses_the_edgar_cik_map` cubren los respaldos.

`scripts/measure_f7_price_sync.py` (Windows/Python 3.12, base temporal) mide lo mismo
antes y después, como se espera de un traslado: sesión ya comprobada 2,23 s con la
referencia capturada y 2,28 s con `data_fetch.sync_prices`.

Inventario: 66 módulos planos = 18 congelados + 37 permanentes + 11 pendientes.
`data_fetch`, `data_quality` e `history_refresh` pierden sus dependencias de las
fachadas retiradas.
