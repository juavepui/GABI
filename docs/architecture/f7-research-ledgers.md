# Research Lab y validación ciega sin storage (F7.23, #133)

Primera entrega de #133. Los dos registros de investigación (experimentos y
validaciones ciegas) dejan la fachada `storage`. La huella de entorno pasa a un
proveedor:

| Fachada | Antes | Ahora |
| --- | --- | --- |
| `research_lab` (registro) | SQL propio sobre `storage.get_connection` | `infrastructure/storage/experiment_log.SqliteExperimentLog` sobre `config.DB_PATH`; fila y detalle en `application/research/experiment_log` |
| `research_lab` (entorno) | `subprocess` (git), `importlib.metadata`, `hashlib` | `infrastructure/providers/research_environment` (`git_commit`, `dependency_versions`, `lock_fingerprint`) |
| `blind_validation` | SQL propio y `storage.get_prices_multi` | `infrastructure/storage/blind_ledger.SqliteBlindLedger` y `cached_data.prices_multi`, ambos sobre `config.DB_PATH` ([ADR 0005](../adr/0005-legacy-config-path.md)) |
| `app_mode` | importaba de forma diferida `research_lab` y `blind_validation` | lee `SqliteExperimentLog` y `SqliteBlindLedger` directamente |

Se conserva la interfaz publicada que usan los motores congelados (`cross_section_test`,
`r3_experiment`, `overfitting_audit`, `factor_history`, `block_bootstrap`,
`rank_stability`) y `smallmid_test`:

- `research_lab`: `log_experiment`, `list_experiments`, `get_experiment`,
  `delete_experiment`, `list_families`, `SCHEMA`, `STAGES`, `STAGE_INFO`,
  `TRACKED_PACKAGES`, `_current_git_commit`, `_dependency_versions`,
  `_env_fingerprint` y `_ensure_columns`.
- `blind_validation`: sus funciones públicas, `SCHEMA` y los mensajes de error.

`log_experiment` y las validaciones llaman a esas funciones de entorno a través del
módulo, así que los parches de pruebas y motores siguen aplicándose. La ruta de la
base se lee en cada operación desde `config.DB_PATH`: los motores que la cambian por
variante siguen escribiendo en su copia.

## ADR 0005

`blind_validation` no importaba `config` y solo necesitaba `storage` para resolver
la ruta. La guarda impedía añadir `config`. [ADR 0005](../adr/0005-legacy-config-path.md)
permite sustituir `gabi.storage` por `gabi.config` en el mismo cambio, sin que crezca
el inventario. `baseline_growth` solo acepta esa sustitución. Lo mismo servirá para
`sync_state` y `price_sync` en #134.

## Efectos

- Las escrituras crean el esquema y las columnas tardías como antes, activan WAL y
  usan un timeout de 30 s.
- Las lecturas (`list_experiments`, `get_experiment`, `list_families`,
  `list_validations`, `get_status`, `verify_integrity`, el estado del modelo) se hacen
  en solo lectura. Ya no crean la base, las tablas ni las columnas tardías. Una tabla
  publicada anterior a `deps_json`/`python_version`/`env_fingerprint`/`data_fingerprint`
  se lee con esas columnas al final y vacías, igual que tras el `ALTER` de antes.
- Un sello ciego y su ranking completo se insertan en una sola transacción. El
  ranking solo se serializa si la validación lo guarda. Un periodo duplicado sigue
  fallando con el mismo mensaje.
- `list_experiments` sigue devolviendo todas las filas, con sus retornos, sin
  límite. `overfitting_audit` (congelado) las recorre todas.

Inventario: −5 dependencias, sin cambio en el número de módulos (70).
`blind_validation` sustituye `gabi.storage` por `gabi.config`.

## Validación y medida

`fixtures/research_ledgers_migration.json` captura `research_lab`, `blind_validation`
y `app_mode` de `c324aabadf3c7b517129f5cd55ffff880921d865`.
`test_research_ledgers_migration.py` ejecuta el código capturado dentro del paquete,
con reloj, commit y entorno fijos, y compara:

- **Registro de experimentos:** etapas válidas e inválidas, todos los campos,
  retornos desordenados con huecos, pesos y resultados vacíos, filtros, detalle,
  familias y borrado. Se comparan los resultados y las tablas (esquema y filas).
- **Tabla publicada sin columnas tardías:** lectura sin modificarla y escritura
  posterior.
- **Validación ciega:** creación con errores, rebalanceos con candidata sin
  cobertura, duplicados, ranking completo opcional, integridad, estados
  bloqueados y revelados con corte por fecha, ruptura del sello, exportación y
  listado, con sus tablas.
- **Lecturas sin base:** no la crean.
- **Estado del modelo:** seis escenarios.
- **Proveedor de entorno.**

Trece mutaciones deliberadas (orden de columnas tardías y de filas, filtro de
familias, borrado, huecos y orden de retornos, pesos vacíos, orden y ranking de
periodos, existencia al activar el ranking, cobertura mínima, señal fuerte del
modelo y longitud de la huella) hacen fallar pruebas. La guarda tiene pruebas de la
sustitución permitida y de las rechazadas.

Medida: `.venv/Scripts/python.exe scripts/measure_f7_research_ledgers.py`.
Windows/Python 3.13, 2.000 experimentos con 240 retornos cada uno y una validación
de 40 periodos, resultados idénticos. Mediana de 5 en dos ejecuciones:

| Lectura | Anterior (s) | Nuevo (s) |
| --- | --- | --- |
| `list_experiments` | 0,051 / 0,054 | 0,051 / 0,054 |
| `get_experiment` | 0,0033 / 0,0034 | 0,0033 / 0,0027 |
| `get_status` (revelado) | 0,582 / 0,601 | 0,599 / 0,588 |

Sin cambio apreciable.

## Segunda entrega: comandos de reproducción ([ADR 0002](../adr/0002-reproducible-research-commands.md))

Clasificación de los módulos de #133 que tenían o tienen una orden propia:

| Módulo | Clase | Ahora |
| --- | --- | --- |
| `historical_validation` (#33) | reproduce `docs/historical-validation-2010-2015` (no sellado) | `gabi_cli research historical-validation`; puente `infrastructure/legacy/historical_validation`; el módulo pierde `main` y `storage` (SPY con `cached_data` sobre `config.DB_PATH`, que `analyze` sigue apuntando al snapshot) |
| `historical_revalidation` (#35) | reproduce `docs/historical-revalidation-2011-2025` (no sellado; `PROTOCOL.md` cita la orden antigua y no se edita) | `gabi_cli research historical-revalidation`; el control de hechos SEC desactualizados lee `SqliteIssuerFactsFreshness` en solo lectura |
| `smallmid_feasibility` (#44) | reproduce `docs/smallmid-feasibility` (no sellado) | `gabi_cli research smallmid-feasibility`; la consulta constante `SELECT '2025'` pasa a ser el literal `2025` |
| `smallmid_test` (#44) | prueba prospectiva preregistrada y en curso (`PREREGISTRO*.md`, huella de funciones `69efba58…`, datos aún sin congelar) | se queda; sus `--rankings`/`--analyze` no son reproducción y sus tareas periódicas lo usan |
| `rotation_experiment` | sellado (`protocol.json`, `audit.json`) | ya era `gabi_cli research rotation-experiment` (excepción del ADR 0002) |
| `value_hypothesis` | sellado (`preregistro.json`) | ya era `gabi_cli research value-hypothesis`; adaptador fino de `spec_hash` |
| `variant_validation`, `evidence_confidence`, `evidence_catalog` | bibliotecas sin orden propia (motores congelados, API) | sin cambio en esta entrega |

Los tres módulos trasladados siguen en su sitio porque los importan motores congelados
(`cross_section_test`, `factor_zoo`, `placebo_engine`, `tail_effect_test`,
`r3_experiment`) o `smallmid_test`. Ni `historical_validation.py` ni
`historical_revalidation.py` figuran en las fuentes que determinan una caché
(`extra_sources`), así que quitar su `main` no invalida rankings. Su
`analysis_sha256` ya no era el publicado: cada README indica la orden y el commit
originales (`3e43efb` y `58a2ed3`). Inventario: los tres pierden `gabi.storage`.

Cambio de comportamiento acotado: sin las tablas de identidad, `stale_issuer_facts`
lanza `ValueError` sin crear la base, en lugar de `sqlite3.OperationalError`.

Validación: `test_research_commands_migration.py` con
`research_commands_migration.json` (código de `dc63e5d`). Ejecuta el `main` capturado
de cada módulo y el subcomando nuevo con los motores sustituidos por registradores:
mismas llamadas, mismos argumentos y mismos bytes impresos (incluido el recorte a
4.000 caracteres de `--summarize`). Compara `stale_issuer_facts` capturado y nuevo
sobre una base temporal, comprueba que la serie SPY se lee del snapshot redirigido y
que los artefactos publicados de #33 y #35 conservan los hashes que registran
(`audit.json`, `summary.json`). Una mutación deliberada del filtro de niveles
acreditados hace fallar la prueba. El acceso a datos no cambia: las dos consultas se
hacen en una transacción de lectura.
Validación del 2026-10-14: suite Python completa de 2.109 pruebas correcta.

## Tercera entrega: inventario de #133

Reducciones (−6 dependencias):

| Módulo | Sale del inventario | Ahora |
| --- | --- | --- |
| `live_ledger` | `os`, `sys` | bloqueo de un solo escritor y ancla atómica en `infrastructure/storage/live_ledger_files` (`_locked` y `_write_anchor` se conservan como envoltorios, porque las pruebas los sustituyen) |
| `live_ledger` | `subprocess` | `research_environment.working_tree_modified` (mismo `git status --porcelain`; solo `OSError` da `None`, como antes) |
| `live_ledger`, `evidence_confidence` | `history_refresh.last_completed_session` | `domain.market.freshness.market_date`, al que también delega `history_refresh` |
| `blind_validation` | `research_lab._current_git_commit` | `research_environment.git_commit(config.BASE_DIR)`, el mismo proveedor que usa `research_lab` |

`live_ledger.py` y `evidence_confidence.py` forman parte de los hashes de
`live_ledger.model_metadata`. La pila ya cambia `live_ledger.py`, `screener.py` y
`edgar.py`, así que `model_version` cambia una sola vez al integrarla; esta entrega no
añade otro cambio de versión.

Excepciones que quedan, justificadas:

| Módulo | Dependencias | Motivo |
| --- | --- | --- |
| `research_lab` | `config`, `pandas` | ruta por operación (ADR 0005); interfaz publicada en `DataFrame` que usan seis motores congelados |
| `blind_validation` | `config`, `research_lab.log_experiment`, `screener_asof`, `pandas` | exporta al registro público de experimentos; los rankings ciegos usan el motor histórico, cuyas entradas explícitas son #132 |
| `app_mode` | `config` | ruta por operación (ADR 0005) |
| `evidence_confidence` | `app_mode`, `config`, `evidence_catalog`, `live_ledger`, `rank_stability`, `scoring` | modelo congelado, catálogo publicado, metadatos del modelo y `rank_stability` (motor reubicado); mover estos ficheros cambia `model_version` |
| `evidence_catalog` | `config`, `factor_sector_stability` | lee factores publicados por un motor congelado |
| `live_ledger` | `app_mode`, `config`, `evidence_confidence`, `identity`, `research_lab`, `screener`, `numpy`, `pandas` | decisión LIVE_FORWARD con el screener vigente y la misma huella de entorno que el laboratorio. Su orden `--verify`/`--recover-anchor` es administración, no reproducción: queda para #135 |
| `variant_validation` | `portfolio_backtest` | biblioteca de `r3_experiment` (congelado) y `rotation_experiment` |
| `value_hypothesis` | `scoring` | adaptador fino de `spec_hash` para un preregistro sellado (ADR 0002) |
| `rotation_experiment` | motores antiguos y `shutil` | excepción explícita del ADR 0002: parchea motores congelados sobre una copia del snapshot |
| `historical_validation`, `historical_revalidation` | `full_universe_audit`, `overfitting_audit`, `multifactor_backtest`, `historical_pit`, `identity`, `scoring`… | motores que importan `cross_section_test`, `factor_zoo`, `placebo_engine`, `tail_effect_test` y `r3_experiment`; `analyze` apunta `config.DB_PATH` al snapshot congelado (comportamiento previo, no ampliado) |
| `smallmid_feasibility` | `historical_issuer_evidence`, `historical_membership`, `historical_tiingo`, `identity`… | estudio publicado que importa `smallmid_test` |
| `smallmid_test` | `storage`, `requests`, `yfinance` y motores históricos | prueba #44 preregistrada y en curso (los datos se congelan como tarde el 15 de enero de 2027; huella de funciones `69efba58…`). Se revisa al cerrarse #44; hasta entonces no se refactoriza |

Con esto `storage.get_connection` solo tiene un uso fuera de `storage`
(`smallmid_test`), y #133 no deja comandos de reproducción en módulos planos.

Validación: `test_research_inventory_migration.py` (bloqueo exclusivo y liberado,
bytes del ancla en modo texto como antes, reglas de fallo de `git status`, fecha de
mercado igual en los cuatro nombres y el mismo commit en laboratorio y validación ciega).
Validación del 2026-10-14: suite Python completa de 2.116 pruebas correcta.
