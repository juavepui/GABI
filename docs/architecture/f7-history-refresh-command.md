# Refresco de datos como comando de investigación (F7.28, #90/#91)

`history_refresh` deja de ser un módulo plano. El refresco completo de fuentes
gratuitas pasa a `python -m gabi_cli research history-refresh`
([ADR 0002](../adr/0002-reproducible-research-commands.md)); sigue exigiendo el registro
de composición revisado hasta el día de ejecución y hace la copia de SQLite y de los CSV
antes de escribir.

| Pieza | Ahora |
| --- | --- |
| Símbolos del periodo, cambios de ticker revisados, CIK por símbolo y bloqueos por identidad, fin de descarga, cuándo reemplazar una serie, serie completa con splits, filas de la grafía con punto de BRK.B/BF.B | `domain/research/history_refresh.py` |
| Orden de pasos, informe y recuentos | `application/research/history_refresh.refresh` con `RefreshPorts` (reloj, registro, ficheros de la ejecución, fuentes, SQLite, EDGAR, fundamentales, FRED) |
| Carpeta de la ejecución (informe, copias, página, CSV publicados), `refresh_prices`, `restore_share_class_spelling`, `database_coverage` y la composición | `infrastructure/legacy/history_refresh.py` |
| Argumentos | `gabi_cli/research/bootstrap.py` (`history-refresh`) |

Consumidores: `infrastructure/legacy/evidence.py` y `live_ledger.py` usan
`domain.market.freshness.market_date`, que era lo que devolvía
`history_refresh.last_completed_session`; `historical_backfill.py` usa
`period_symbols` del dominio y `database_coverage` del puente. Ningún motor congelado,
huella publicada ni `model_version` leía el módulo por nombre: las apariciones de
`history_refresh` en motores congelados son la carpeta `data/history_refresh/`.

`docs/data-refresh-2026-09-23/README.md` (no sellado) cita la ruta nueva y el commit
`c324aab` de `develop` con el módulo original. No se regeneran datos ni documentos.

## Pruebas

- `test_history_refresh_migration`: ejecuta el módulo capturado
  (`fixtures/history_refresh_migration.json`) y el nuevo con las mismas fuentes
  sintéticas (Wikipedia, EDGAR, Yahoo con un fallo y un split, FRED con un error que
  contendría la clave). Coinciden el informe devuelto y el escrito, los ficheros de la
  carpeta de la ejecución, los CSV de composición, todas las tablas de SQLite, el orden
  de las llamadas a las fuentes y la salida. También comprueba que sin registro
  revisado hasta hoy no se crea ninguna carpeta.
- Las pruebas de `refresh_prices`, de la grafía de clases de acciones y de la cobertura
  usan el puente; las de fecha de mercado usan `freshness.market_date`.

Inventario: 63 módulos planos = 18 congelados + 37 permanentes + 8 pendientes.
