# Inventario de compatibilidad permanente (#135)

Lista cerrada de los módulos planos de `backend/src/gabi` que no están congelados
([ADR 0006](../adr/0006-permanent-compatibility-inventory.md)). La fuente es
[`architecture-compatibility.json`](../../.github/architecture-compatibility.json);
`scripts/check_architecture.py` comprueba que cubre todos los módulos, que los
permanentes no usan SQL, HTTP ni procesos salvo la excepción declarada y que los
pendientes solo bajan.

El [balance F7](f7-balance.md) contrasta el estado integrado con los archivos y
documenta la evidencia de cierre. La clasificación introducida el 2026-10-14
(F7.25–F7.33), integrada en `5467954`, conserva 58 módulos planos =
18 congelados + 40 permanentes + 0 pendientes. `pending` queda vacío:

- se retiran `price_sync`, `macro` e `insider` ([F7.25](f7-retire-source-facades.md)),
  `blind_validation` ([F7.26](f7-retire-blind-validation.md)), `historical_identity_audit`
  ([F7.27](f7-identity-audit-command.md)), `history_refresh`
  ([F7.28](f7-history-refresh-command.md)), `sync_state` ([F7.29](f7-retire-sync-state.md)),
  `data_fetch` ([F7.30](f7-retire-data-fetch.md)), `sec_history`
  ([F7.31](f7-sec-history-command.md)), `data_quality` ([F7.32](f7-retire-data-quality.md))
  y `app_mode` ([F7.33](f7-retire-app-mode.md));
- `historical_archive`, `historical_tiingo` y `historical_wiki` pasan a permanentes porque
  los importa la prueba #44 preregistrada (decisión del 2026-10-14).

## Criterio de cierre de #90 y #91

1. `pending` vacío: cada módulo pendiente se retira o pasa a permanente con su motivo.
2. Todo módulo plano restante es congelado o permanente sin I/O directo. Las dos
   excepciones de la prueba #44 (`smallmid_test` y el `get_connection` de `storage`)
   se cierran al terminar #44, como tarde tras congelar sus datos el 2027-01-15.
   Entonces se revisan también `historical_archive`, `historical_tiingo` y
   `historical_wiki`, permanentes solo porque `smallmid_test` los importa.

## Congelados (18)

Verificados por hash con `gabi_cli research frozen --check-frozen`: `block_bootstrap`, `capital_input_audit`, `capital_input_audit_v2`, `config`, `cross_section_test`, `factor_benchmark`, `factor_history`, `factor_sector_stability`, `factor_stability`, `factor_zoo`, `full_universe_audit`, `overfitting_audit`, `placebo_engine`, `r3_experiment`, `rank_stability`, `repurchase_cash_strategy`, `strategy_discovery`, `tail_effect_test`.

## Permanentes (40)

"Leído por nombre" significa que un fichero congelado, una caché o un documento
publicado registra el hash del fichero por su nombre: debe seguir existiendo aunque
delegue. "Interfaz de motores congelados" significa que un motor congelado lo
importa y usa sus nombres públicos.

| Módulo | Motivo | Consumidores | I/O directo |
| --- | --- | --- | --- |
| `academic_factors` | interfaz de motores congelados | block_bootstrap (congelado); cross_section_test (congelado); factor_benchmark (congelado); factor_history (congelado); factor_stability (congelado); r3_experiment (congelado); tail_effect_test (congelado) | ninguno |
| `edgar` | interfaz de motores congelados; leído por nombre para una huella publicada | cross_section_test (congelado); r3_experiment (congelado); overfitting_audit (huella de código); live_ledger.model_metadata (model_version); historical_validation/historical_revalidation.extra_sources (audit.json publicados) | ninguno |
| `entity_master` | leído por nombre para una huella publicada | overfitting_audit (huella de código) | ninguno |
| `evidence_catalog` | interfaz de motores congelados; leído por nombre para una huella publicada | factor_sector_stability (congelado); live_ledger.model_metadata (model_version) | ninguno |
| `evidence_confidence` | leído por nombre para una huella publicada | live_ledger.model_metadata (model_version) | ninguno |
| `historical_archive` | interfaz de la prueba #44 preregistrada: smallmid_test (SHA-256 en PREREGISTRO-A1..A3) lo importa; se revisa al terminar #44, como tarde tras congelar sus datos el 2027-01-15 | smallmid_test (#44); historical_revalidation; historical_membership; historical_tiingo; historical_wiki; infrastructure/legacy/data_health; infrastructure/legacy/sec_validation; infrastructure/legacy/sec_history | ninguno |
| `historical_issuer_evidence` | leído por nombre para una huella publicada | historical_validation/historical_revalidation.extra_sources (audit.json publicados) | ninguno |
| `historical_membership` | leído por nombre para una huella publicada | historical_validation/historical_revalidation.extra_sources (audit.json publicados) | ninguno |
| `historical_period` | leído por nombre para una huella publicada | historical_validation/historical_revalidation.extra_sources (audit.json publicados) | ninguno |
| `historical_pit` | interfaz de motores congelados; leído por nombre para una huella publicada | cross_section_test (congelado); r3_experiment (congelado); historical_validation/historical_revalidation.extra_sources (audit.json publicados) | ninguno |
| `historical_price_audit` | leído por nombre para una huella publicada | historical_validation/historical_revalidation.extra_sources (audit.json publicados) | ninguno |
| `historical_price_policy` | leído por nombre para una huella publicada | historical_validation/historical_revalidation.extra_sources (audit.json publicados) | ninguno |
| `historical_revalidation` | comando de reproducción #35 (ADR 0002); interfaz de motores congelados | gabi_cli research historical-revalidation; cross_section_test (congelado); factor_zoo (congelado); placebo_engine (congelado); r3_experiment (congelado); tail_effect_test (congelado) | ninguno |
| `historical_ticker_corrections` | leído por nombre para una huella publicada | historical_validation/historical_revalidation.extra_sources (audit.json publicados) | ninguno |
| `historical_tiingo` | interfaz de la prueba #44 preregistrada: smallmid_test (SHA-256 en PREREGISTRO-A1..A3) lo importa; se revisa al terminar #44, como tarde tras congelar sus datos el 2027-01-15 | smallmid_test (#44); smallmid_feasibility; historical_price_audit; infrastructure/legacy/periodic | ninguno |
| `historical_validation` | comando de reproducción #33 (ADR 0002); interfaz de motores congelados | gabi_cli research historical-validation; cross_section_test (congelado) | ninguno |
| `historical_wiki` | interfaz de la prueba #44 preregistrada: smallmid_test (SHA-256 en PREREGISTRO-A1..A3) lo importa; se revisa al terminar #44, como tarde tras congelar sus datos el 2027-01-15 | smallmid_test (#44); historical_price_audit | ninguno |
| `identity` | interfaz de motores congelados; leído por nombre para una huella publicada | full_universe_audit (congelado); overfitting_audit (congelado); overfitting_audit (huella de código); full_universe_audit (huella de cachés); rotation_experiment (protocol.json/audit.json sellados) | ninguno |
| `live_ledger` | leído por nombre para una huella publicada | live_ledger.model_metadata (model_version) | ninguno |
| `membership_extension` | leído por nombre para una huella publicada | historical_validation/historical_revalidation.extra_sources (audit.json publicados) | ninguno |
| `metrics` | leído por nombre para una huella publicada | live_ledger.model_metadata (model_version) | ninguno |
| `multifactor_backtest` | interfaz de motores congelados; leído por nombre para una huella publicada | full_universe_audit (congelado); overfitting_audit (congelado); overfitting_audit (huella de código); full_universe_audit (huella de cachés) | ninguno |
| `portfolio_backtest` | interfaz de motores congelados; leído por nombre para una huella publicada | full_universe_audit (congelado); r3_experiment (congelado); full_universe_audit (huella de cachés); rotation_experiment (protocol.json/audit.json sellados) | ninguno |
| `portfolio_metrics` | interfaz de motores congelados | full_universe_audit (congelado) | ninguno |
| `research_lab` | interfaz de motores congelados | block_bootstrap (congelado); cross_section_test (congelado); factor_history (congelado); overfitting_audit (congelado); r3_experiment (congelado); rank_stability (congelado) | ninguno |
| `risk` | interfaz de motores congelados; leído por nombre para una huella publicada | r3_experiment (congelado); overfitting_audit (huella de código); live_ledger.model_metadata (model_version) | ninguno |
| `rotation_experiment` | comando de reproducción sellado (ADR 0002): parchea motores congelados sobre una copia del snapshot | gabi_cli research rotation-experiment | ninguno |
| `rotation_policy` | leído por nombre para una huella publicada | rotation_experiment (protocol.json/audit.json sellados) | ninguno |
| `scoring` | interfaz de motores congelados; leído por nombre para una huella publicada | cross_section_test (congelado); factor_history (congelado); factor_zoo (congelado); full_universe_audit (congelado); overfitting_audit (congelado); placebo_engine (congelado); r3_experiment (congelado); rank_stability (congelado); overfitting_audit (huella de código); full_universe_audit (huella de cachés); live_ledger.model_metadata (model_version) | ninguno |
| `screener` | leído por nombre para una huella publicada | live_ledger.model_metadata (model_version) | ninguno |
| `screener_asof` | interfaz de motores congelados; leído por nombre para una huella publicada | full_universe_audit (congelado); overfitting_audit (congelado); r3_experiment (congelado); overfitting_audit (huella de código); full_universe_audit (huella de cachés) | ninguno |
| `smallmid_feasibility` | estudio publicado docs/smallmid-feasibility que importa la prueba #44 | smallmid_test; gabi_cli research smallmid-feasibility | ninguno |
| `smallmid_test` | prueba #44 preregistrada y en curso (PREREGISTRO-A1..A3, huella de funciones 69efba58…); los datos se congelan como tarde el 2027-01-15 | tareas periódicas Tiingo; infrastructure/legacy/smallmid | `requests`, `yfinance` |
| `stats_rigor` | interfaz de motores congelados | overfitting_audit (congelado); placebo_engine (congelado); r3_experiment (congelado) | ninguno |
| `storage` | leído por nombre para una huella publicada; get_connection solo para smallmid_test (#44) | smallmid_test; overfitting_audit (huella de código) | `sqlite3` |
| `technicals` | leído por nombre para una huella publicada | overfitting_audit (huella de código); live_ledger.model_metadata (model_version) | ninguno |
| `universe` | interfaz de motores congelados; leído por nombre para una huella publicada | full_universe_audit (congelado); overfitting_audit (congelado); overfitting_audit (huella de código); historical_validation/historical_revalidation.extra_sources (audit.json publicados) | ninguno |
| `value_hypothesis` | adaptador fino de spec_hash para el preregistro sellado docs/value-hypothesis (ADR 0002) | gabi_cli research value-hypothesis; API de preregistros | ninguno |
| `variant_validation` | interfaz de motores congelados; leído por nombre para una huella publicada | r3_experiment (congelado); rotation_experiment (protocol.json/audit.json sellados) | ninguno |
| `workspace` | leído por nombre para una huella publicada | live_ledger.model_metadata (model_version) | ninguno |

## Pendientes (0)

Ninguno. El primer punto del criterio de cierre se cumple.

## `model_version` del ledger

`live_ledger.model_metadata` sigue hasheando las fachadas (`scoring`, `metrics`,
`technicals`, `risk`, `screener`, `edgar`, `live_ledger`, `evidence_confidence`,
`evidence_catalog`, `workspace`, `__init__`) junto con los módulos de dominio y
aplicación con la lógica. Las fachadas trasladan parámetros de `config` y algunas aún
contienen lógica (ADR 0006, punto 5). Cualquier cambio en ellas produce una
`model_version` nueva; la pila #122→#144 la cambia una vez al integrarse.
