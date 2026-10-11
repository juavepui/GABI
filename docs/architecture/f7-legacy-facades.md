# Fachadas con dependencias legacy (F7.14)

Cinco fachadas mutables dejan de abrir SQL o de pasar por `storage`, y el
inventario `.github/architecture-legacy.json` pierde trece dependencias. Las
interfaces públicas se conservan; los motores congelados no cambian.

| Fachada | Ahora delega en | Dependencias retiradas |
| --- | --- | --- |
| `edgar_sync` | `edgar.synchronize_issuer`: `SqliteXbrl`, `OperationSyncEvents` y `SyncAttempt`, la composición del worker | `identity`, `storage`, `sync_state` (y `edgar`→`edgar_sync`) |
| `entity_master` | `application/market/sector_snapshots.py`, regla en `domain/market/sector_snapshots.py`, `SqliteEntitySnapshots` vía `identity.sector_snapshots()` | `storage` |
| `screener` | `cached_data`/`SqliteCacheReads`, `sec_reads.cached_metrics`, `SqliteFred.history`, `domain.market.fundamentals` | `macro`, `metrics`, `storage` |
| `live_ledger` | `infrastructure/storage/live_ledger_writes.py` (SQL del ledger), `cached_data.latest_adjusted` y lectores de procedencia | `edgar`, `storage` |
| `history_refresh` | `SqliteCacheReads.table_coverage`, `SqliteSecReads.stored_ciks`, `SqliteCacheWrites`, `backups.backup_once` | `storage`, `sqlite3` |

Para retirar `storage` de `history_refresh` sin copiar SQL, las escrituras de
`storage` (`init_db`, `upsert_prices`, `upsert_splits`, `upsert_fundamentals`,
`record_update_errors`) delegan en `SqliteCacheWrites`
(`infrastructure/storage/cache_writes.py`), con ruta y reloj explícitos. `storage`
pierde además `identity.put_observations`. `get_connection`, `_ensure_price_columns`
y `_df_to_json` se mantienen para sus consumidores. `backup_once` pasa de
`sec_quarter_ingest` a `infrastructure/storage/backups.py`.

## Contratos conservados

- Mismas filas, columnas, unidades, atribuciones `yahoo:explicit-entity`,
  `fetched_at`, poda de 90 días de `update_errors` y alteración de la columna
  `adj_close` en tablas antiguas al escribir. Las escrituras usan la misma
  conexión (WAL, 30 s) y la atribución fallida revierte las filas de precios.
- `edgar_sync.run_one` produce los mismos resultados, eventos y checkpoints
  que la composición moderna, verificada contra la fachada original en
  `test_sec_xbrl_migration.py`. Las escrituras de hechos y métricas son ahora
  una sola transacción (`SqliteXbrl.save`) en lugar de dos.
- `entity_master` conserva la elección de foto (última hasta la fecha o la
  más antigua marcada aproximada), el aislamiento por entidad y la tabla legacy
  solo para símbolos sin alias. La escritura de fotos y observaciones es una
  transacción.
- `live_ledger` conserva el esquema con triggers append-only, `BEGIN IMMEDIATE`,
  verificación, ancla y recuperación; solo cambia dónde vive el SQL. La
  procedencia lee el último cierre con `adj_close>0` por símbolo, como antes.
- `history_refresh` conserva cobertura, restauración BRK.B/BF.B, refresco de
  precios con splits y su copia `gabi_before.db`.

## Cambios de efecto

- Lecturas sin `CREATE`/`ALTER` ni creación de base: cobertura, CIK guardados,
  procedencia, ranking de la fachada `screener` y fotos de sector. Una tabla
  ausente cuenta como vacía; antes `database_coverage` fallaba sin `edgar_facts`
  o `macro_series`.
- El hash de código de `live_ledger.model_metadata` incluye `screener.py`,
  `edgar.py` y `live_ledger.py`; las decisiones capturadas después de este
  cambio tendrán otra `model_version`, como tras cada cambio F7 anterior. La
  reproducción de decisiones no depende de ese hash. La caché local de
  `overfitting_audit` también registra hashes de `edgar.py`, `storage.py` y
  `entity_master.py`; una caché no publicada debe regenerarse.

Siguen pendientes: `sync_state.retry`/`fingerprint` (aún vía `sync_state`), las
llamadas de `entity_master` a `identity`/`edgar`, los proveedores de
`history_refresh` (Yahoo, Wikipedia, SEC, FRED) y las dependencias de
`technicals`, `risk` y `scoring` en `screener`, que traducen `config` a
parámetros de dominio.

## Validación y medida

Referencia `c324aabadf3c7b517129f5cd55ffff880921d865` en
`fixtures/legacy_facades_migration.json`. `test_legacy_facades_migration.py`
(20 pruebas) compara con el código capturado: escrituras de `storage` con y sin
`adj_close`, conexión legacy prohibida y reversión de atribución; `edgar_sync`
contra la composición moderna tabla a tabla; `get_sector_asof` en tres fechas y
modo estricto; `record_snapshot` con y sin fecha; tabla de `screener` con dos
pesos y tipo libre de riesgo; cadena, ancla, recuperación y triggers del ledger;
procedencia; cobertura, restauración y refresco de `history_refresh`. Tres
mutaciones deliberadas (foto, filtro de cierre y retención) hacen fallar
pruebas. `test_storage.py` y `test_membership_extension.py` cambian sus
monkeypatch de detalles internos (`storage.timedelta`, `history_refresh.storage`)
por los nuevos puntos de inyección, sin cambiar lo que comprueban.

Medida: `.venv/Scripts/python.exe scripts/measure_f7_legacy_facades.py`.
Windows/Python 3.13, 200 símbolos de 250 sesiones; paridad exacta y cero descargas.

| Flujo | Frío anterior → nuevo (s) | Mediana caliente (s) | Pico Python (MiB) | Conexiones | Esquema |
| --- | --- | --- | --- | --- | --- |
| Escritura de precios y splits | 2,8289 → 2,8619 | 2,8511 → 2,8527 | 0,48 → 0,42 | 400 → 400 | 2.000 → 2.000 |
| Procedencia del ledger | 0,0169 → 0,0121 | 0,0171 → 0,0120 | 1,62 → 0,09 | 3 → 3 | 5 → 0 |

Las escrituras mantienen su coste: siguen inicializando su esquema en cada
operación, como antes. La procedencia deja de escribir esquema y materializa menos.
