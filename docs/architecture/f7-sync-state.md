# Errores de fuente, reintentos y checkpoints (F7.15)

`sync_state` y la clasificación de errores de `data_fetch` eran dependencias del
núcleo legacy de casi todas las fuentes. Ahora delegan en capas nuevas y
conservan su interfaz.

- `domain/market/source_errors.py`: `classify(mensaje, servicio)`,
  `RETRYABLE_CATEGORIES` y `retry_wait` (espera exponencial 1,5·2ⁱ, elevada a un
  `Retry-After` numérico y acotada a 30 s).
- `domain/market/sync_events.py`: además de la política de evento/checkpoint,
  `fingerprint`, `due(checkpoint, horas, now)` y `totals`.
- `application/administration/sync_events.py`: `retry` con transitoriedad,
  `Retry-After`, ritmo y espera inyectados, junto a `SyncAttempt`.
- `infrastructure/storage/sync_events.py`: `OperationSyncEvents` añade
  `events_since`, `latest_event_id` y `failed_datasets` de solo lectura y acotadas.

`sync_state` compone esas piezas: `get`, `Attempt` (ahora un `SyncAttempt`),
`due`, `retry`, `events_since`, `latest_event_id`, `failed_datasets`,
`fingerprint` y `totals`. Conserva el único marcapasos por fuente del proceso
(`_pace`) y la vista `requests` de fallo transitorio: ADR 0003 no permite que un
módulo plano importe proveedores, y dos marcapasos podrían superar el límite de
la SEC. El puente `infrastructure/legacy/source_errors.py` sigue usando ese
`retry`; su clasificación y huella vienen ya del dominio.

`data_fetch._classify_error` delega en `classify`. `edgar`, `macro`, `insider` y
los puentes de beneficios, estimaciones e insiders usan la regla de dominio
directamente. El puente `periodic` usa `OperationSyncEvents` de su `data_dir`
explícito, `SyncAttempt` y las reglas de dominio, sin `sync_state`. Como
`sync_state` no puede importar `config`, `storage.database_path()` da la ruta de
compatibilidad por operación. Inventario: −5 dependencias (`data_fetch.*` en
`edgar`, `insider`, `macro` y `sync_state`).

## Contratos y efectos

- Misma categoría y mensaje para cada error, mismos intentos, llamadas
  contadas, esperas de ritmo y de reintento, excepciones finales y huellas.
- Mismos checkpoints y eventos: marca de agua máxima, éxito no avanzado por un
  fallo, redacción de `api_key`/`token`, eventos omitidos sin checkpoint.
- Las lecturas de checkpoints y eventos ya no crean la base ni el esquema; una
  base ausente devuelve `{}`, `[]`, `0` o `set()`. Las escrituras inicializan su
  esquema y aplican el límite de 2 MB de `SqliteSyncEvents` por checkpoint/evento.
- `Attempt` deja de ser una dataclass: conserva constructor posicional,
  `calls`, `payload_bytes`, `payload` y `finish`.

## Validación y medida

Referencia `c324aabadf3c7b517129f5cd55ffff880921d865` en
`fixtures/sync_state_migration.json`. `test_sync_state_migration.py` (52 pruebas)
compara clasificación con tres servicios y dieciséis mensajes; huella, `due` y
`totals`; checkpoints y eventos tras éxitos, fallos, omisiones y estado inválido;
once escenarios de reintento (timeouts, conexión, 5xx, 429 con `Retry-After`
numérico, grande o inválido, errores no transitorios) con cuatro ritmos y
fuentes; puente de arranque y puente `periodic`. Tres mutaciones deliberadas
(base exponencial, tope y umbral 5xx) hacen fallar doce pruebas.

Medida: `.venv/Scripts/python.exe scripts/measure_f7_sync_state.py`.
Windows/Python 3.13, 500 entidades: lectura de checkpoint, intento terminado,
fallos y eventos. Paridad exacta y cero descargas.

| Flujo | Frío anterior → nuevo (s) | Mediana caliente (s) | Pico Python (MiB) | Conexiones | Sentencias CREATE |
| --- | --- | --- | --- | --- | --- |
| Checkpoints, intentos y eventos | 3,6996 → 2,3523 | 3,7004 → 2,3444 | 1,72 → 1,70 | 1.502 → 1.500 | 4.506 → 1.500 |

La mejora procede de no inicializar esquema al leer en esta fixture; las
escrituras siguen inicializándolo como antes.
