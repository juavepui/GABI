# Retirada de `data_quality` (F7.32, #90/#91)

`data_quality` ya solo componía `domain.market.data_quality` (reglas de calidad,
frescura y procedencia) y `application.administration.data_quality` (resumen del
universo y procedencia por empresa) con los almacenes. Pasa a
`infrastructure/legacy/data_quality.py` con los mismos nombres
(`universe_summary`, `symbol_provenance`, `compute_data_fingerprint`,
`ranking_quality`, `recent_errors_summary`, `local_cik_status`…), y sus consumidores
lo usan desde ahí: `infrastructure/legacy/data_health` y `backtests`.

`multifactor_backtest` (permanente: interfaz de `full_universe_audit` y huella de
`overfitting_audit`) llama a `domain.market.data_quality.ranking_quality`, cuyas
métricas por defecto son exactamente las de `scoring.SCORE_METRICS` que pasaba la
fachada. Ya cambia en la pila, así que no añade otro cambio de huella; sale de su
excepción legacy `gabi.data_quality`.

## Pruebas y medida

- `test_ranking_quality_migration` sigue comparando con la fachada capturada y
  `test_backtest_inputs_migration` con los motores V1/V2 capturados; estos reciben el
  puente como `gabi.data_quality` solo dentro de su prueba, y la calidad sintética se
  sustituye en el puente y en el dominio.
- `scripts/measure_f7_ranking_quality.py` estaba roto desde F7.25 (su captura importaba
  `insider` y `macro`); usa los mismos sustitutos que la prueba y vuelve a dar
  paridad. `measure_f7_backtests.py`: V1 0,042 → 0,040 s; V2 0,053 → 0,053 s.

## Scripts de medida

Un barrido de los 43 `scripts/measure_*.py` y `benchmark_*.py` encontró siete que
ejecutaban código capturado que importaba módulos ya retirados: `data_fetch`,
`sec_history` y `blind_validation` (esta pila), e `historical_data_audit` (#138).
`backend/tests/retired_modules.py` reúne los sustitutos de todos los módulos planos
retirados en F7 (los puentes de `infrastructure/legacy`, `sync_checkpoints` y lectores
equivalentes para `insider`/`macro`), y los scripts llaman a `install()` antes de
ejecutar una captura. Las pruebas siguen inyectando solo el módulo que necesita cada
captura: un registro global ocultaría imports de módulos retirados desde producción.
`measure_f7_historical_data_audit` además fuerza la recolección antes de borrar su
directorio temporal, porque la versión capturada deja la conexión SQLite al
recolector y Windows no deja borrar el fichero abierto. Los 43 scripts terminan sin
error.

Inventario: 59 módulos planos = 18 congelados + 40 permanentes + 1 pendiente.
