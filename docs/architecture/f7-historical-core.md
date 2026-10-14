# Núcleo histórico: periodos acreditados y registros revisados (F7.20, #130)

## Periodos acreditados

`historical_pit.accredited_periods(...)` es la entrada publicada con la que los
motores congelados (`cross_section_test`, `r3_experiment`) y
`historical_revalidation` activan la capa 2016–2025. No se puede eliminar sin
cambiar esos motores, así que se conserva, pero su estado se mueve a `identity`,
que es quien resuelve emisores contra él:

- `identity.accredited_periods`, `identity.active_accredited_periods()` y
  `identity.accredited_history()`; `historical_pit.accredited_periods` es el mismo
  objeto.
- `application/research/historical_pit.AccreditedHistory(reader, periods)` concreta
  el puerto `AccreditedHistory` que ya usaba `application/market/identity`
  (`covers`, `period_for`, `has_series`, `ranking_series`, `holding_series`), con
  periodos explícitos. `QUARTER_ENDS` y `TRAILING_DAYS` viven ahí.
- `identity` deja de importar `historical_pit`: desaparece el ciclo entre ambos.
  `historical_pit` delega en `identity.accredited_history()`.

El código nuevo recibe los periodos como parámetro; el estado global solo existe
para la compatibilidad publicada.

## Registros revisados

`infrastructure/storage/reviewed_resources.py` lee los registros versionados del
paquete (`sp500_extension.json` y las nominaciones de identidad 2010–2015 y
2016–2025) con una única caché de nominaciones. `universe`, `history_refresh`,
`historical_identity_audit` e `historical_price_audit` usan ese cargador y el
dominio (`membership`, `ticker_corrections`, `periods`) en lugar de
`membership_extension`, `historical_ticker_corrections` y `historical_period`.

## Lo que no se puede retirar

`historical_revalidation.extra_sources()` e `historical_validation.extra_sources()`
leen por nombre `historical_period.py`, `historical_membership.py`,
`historical_ticker_corrections.py`, `membership_extension.py`, `historical_pit.py`,
`historical_price_policy.py`, `historical_price_audit.py`,
`historical_issuer_evidence.py`, `universe.py` y `edgar.py` para la huella de
sus cachés; los `audit.json` publicados en `docs/historical-revalidation-2011-2025/`
registran esos hashes. Borrarlos rompería esas funciones, que importan motores
congelados. Por eso `historical_period`, `membership_extension` e
`historical_ticker_corrections` se quedan como alias delgados: ya no tienen
importadores legacy (salvo pruebas), pero sus archivos deben existir. Esta lista
alimenta #135. Como en cada fase F7, editar estos archivos invalida las cachés
locales no publicadas de esas validaciones; los resultados publicados no cambian.

`historical_archive`, `historical_membership` e `historical_price_policy` ya
delegan su I/O en `infrastructure/storage` (F7.7); no queda SQL en ellos.

Inventario: −21 dependencias (`identity` sin `historical_pit`; seis módulos sin
`historical_period`; `universe`, `history_refresh`, `historical_identity_audit` e
`historical_price_audit` sin `membership_extension`/`historical_ticker_corrections`;
dos `pathlib`).

## Validación

`fixtures/historical_core_migration.json` captura `historical_pit.py` de
`c324aabadf3c7b517129f5cd55ffff880921d865`. `test_historical_core_migration.py`
compara `active_periods`, `covers` y `period_for` en siete fechas con cinco
combinaciones de periodos, que el lector de identidad usa los mismos periodos,
que el contexto se restaura tras un error y que los registros revisados se leen
una sola vez. Validación del 2026-10-13: suite Python completa de 2.002 pruebas
correcta. Sin cambio de acceso a datos: no hay tabla de tiempos.
