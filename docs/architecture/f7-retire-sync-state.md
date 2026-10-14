# Retirada de `sync_state` (F7.29, #90/#91)

`sync_state` era la fachada de checkpoints, intentos medidos, reintentos y del
marcapasos único por fuente. Sus piezas ya estaban en dominio, aplicación e
infraestructura (F7.15); ahora sus consumidores las usan directamente:

| Antes | Ahora |
| --- | --- |
| `sync_state.retry`, `_pace`, `_transient`, `_retry_after` (con `requests`) | `infrastructure/providers/source_retry.py`: el mismo marcapasos de proceso (cerrojo y próximo turno por fuente) y el caso de uso `application/administration/sync_events.retry` |
| `sync_state.Attempt` | `infrastructure/storage/sync_events.measured_attempt(events, …)`: `SyncAttempt` con reloj UTC, `perf_counter` y `thread_time` |
| `get`, `events_since`, `latest_event_id`, `failed_datasets` | `OperationSyncEvents(config.DB_PATH)`, con la ruta leída en cada operación |
| `due`, `fingerprint`, `totals` | `domain.market.sync_events` |

Consumidores: `edgar` (mapa CIK, Company Facts por emisor y fallos de la selección
SEC), `data_fetch` (precios y fundamentales), `historical_tiingo` (intentos e
importación) e `infrastructure/legacy/source_errors`, que reexporta `retry` para los
puentes del bootstrap. Como todos reintentan por `source_retry`, el marcapasos sigue
siendo único por proceso.

`edgar` está en huellas registradas (`overfitting_audit`, `model_version`,
`extra_sources`), pero la pila #122→#149 ya lo modifica: esta entrega no añade otro
cambio de huella al integrarla.

## Pruebas y medida

- `tests/sync_checkpoints.py` expone los nombres retirados sobre las mismas piezas
  que usa producción. `test_sync_state_migration` compara con él y con
  `source_retry` el módulo capturado: reglas, checkpoints, eventos, fallos, lecturas
  sin crear la base y reintentos con sus esperas.
- Las capturas antiguas de `edgar`, `data_fetch` y `price_sync` que importaban
  `sync_state` lo reciben como `gabi.sync_state` solo dentro de su prueba.
- `scripts/measure_f7_sync_state.py` (Windows/Python 3.12, base temporal,
  500 entidades): paridad exacta; mediana en caliente 9,77 s con la referencia
  capturada y 5,14 s ahora, con 1.500 conexiones y 1.500 sentencias de esquema frente
  a 1.502 y 4.506.

Inventario: 62 módulos planos = 18 congelados + 40 permanentes + 4 pendientes.
