# Migración de los módulos existentes

Fuente normativa: [arquitectura de GABI](../architecture.md). Este plan aplica sus
reglas al código antiguo sin modificar de golpe cálculos o artefactos publicados.

El [balance vigente de F7](f7-balance.md) es la referencia del estado integrado y
de la evidencia de cierre de #90/#91. Las entregas siguientes describen el avance
histórico; un pendiente citado en ellas no implica que siga pendiente hoy.

## Cómo evolucionar un módulo antiguo

1. Localizar sus consumidores, dependencias y archivos sellados. Capturar una
   fixture aislada y comprobar el comportamiento vigente: identidad, elegibilidad,
   orden, score, costes, fechas, null y unidades según corresponda.
2. Separar cálculo puro, coordinación e I/O en las capas previstas. Crear el caso
   de uso mínimo y su puerto concreto. Una ruta nueva no llama directamente al
   módulo plano: usa el caso de uso y un puente `infrastructure/legacy` si hace falta.
3. Migrar un flujo completo. Todos los adaptadores usan el mismo caso de uso; el nombre
   legacy puede quedar como fachada que delega en `application`/`domain`. No duplicar
   una fórmula para tener dos implementaciones aparentemente equivalentes.
4. Verificar paridad y efectos, medir cuando cambie el camino de datos, retirar
   imports/módulos que ya no se usen y podar sus entradas del baseline. No cambiar
   las excepciones para introducir nuevas dependencias planas.

Los módulos cuyo código está publicado y congelado se mantienen en su ubicación
y con sus bytes. El puente adapta entradas/salidas/rutas por fuera. La arquitectura
aplica a sus nuevos consumidores; su interior queda como excepción identificada.
Una versión nueva del motor es un cambio separado con su procedencia, no una
reorganización silenciosa del original. Los módulos mutable tampoco se trasladan
sin comprobar los manifiestos que los referencian.

Para retirar SQL de una fachada existente, [ADR 0003](../adr/0003-legacy-storage-delegation.md)
permite delegarlo en un módulo concreto de `infrastructure/storage`, con ruta
explícita por operación. No permite nuevos imports de proveedores, ajustes o
puentes legacy; almacenamiento no puede importar módulos planos y los ciclos
con capas nuevas siguen prohibidos. El inventario de excepciones solo disminuye.

[La extracción F7.7](f7-historical-composition-writes.md) aplica ese límite a
los loaders de composición y escritores de auditorías históricas. Las fachadas
mantienen su API; los casos de uso reciben puertos y los adaptadores concretos
ruta/reloj por operación. Sus lecturas no crean esquemas y sus importaciones
revierten también el alta del emisor cuando falla la evidencia.

[F7.8](f7-historical-runners.md) continúa con coordinación de composición,
auditoría/promoción de precios, intervalos y cobertura de identidad,
exportaciones explícitas y respaldo operativo por ticker. Los lectores no
crean esquemas y la caché de precios tiene presupuesto y vida por operación.
[F7.9](f7-historical-issuer-files.md) extrae los lectores de archivos de evidencia,
la preparación por CIK y los cálculos de vida de cotización. Las descargas y
acciones de ingesta conservan su compatibilidad documentada.
[F7.10](f7-sec-archive-download.md) extrae la acción común de descarga y el
registro de procedencia del archivo SEC, conservando la fuente HTTP pequeña
de compatibilidad y las acciones de selección/ingesta todavía pendientes.
[F7.11](f7-sec-bulk-import.md) extrae la importación trimestral SUB/NUM con
lectura local por lotes y migración/escritura atómicas; la selección de CIK,
los checkpoints y el escaneo de identidad mantienen su compatibilidad.
[F7.12](f7-storage-reads.md) retira las escrituras de esquema de las lecturas
de `storage` y de las métricas EDGAR cacheadas; las escrituras siguen en sus fachadas.
[F7.13](f7-sec-quarter-ingest.md) extrae la selección de CIK y de covers, los
checkpoints trimestrales y la recuperación de instancias XBRL del archivo SEC.
[F7.14](f7-legacy-facades.md) retira `storage` y otras dependencias planas de
`edgar_sync`, `entity_master`, `screener`, `live_ledger` e `history_refresh`.
[F7.15](f7-sync-state.md) lleva clasificación de errores, reintentos y checkpoints
a dominio, aplicación e infraestructura; `sync_state` conserva el marcapasos único.
[F7.16](f7-edgar-writes.md) retira `storage` de `edgar` (escrituras, resoluciones CIK)
y extrae Company Facts por CIK de `sec_history`.
[F7.17](f7-http-providers.md) aplica [ADR 0004](../adr/0004-legacy-provider-delegation.md):
las fachadas delegan su HTTP en proveedores acotados de `infrastructure/providers`.
[F7.18](f7-yahoo-provider.md) concentra `yfinance` en `infrastructure/providers/yahoo.py`.
`edgar_sync` se retira: ya no tenía consumidores de producción y su única
función delegaba en `edgar.synchronize_issuer`, que usan sus pruebas.
[F7.19](f7-operational-sources.md) (#134) saca `macro`, `insider`, `price_sync` y
`data_fetch` de la fachada `storage` y rompe el ciclo `data_fetch`↔`price_sync`;
su segunda entrega lee la ruta de `sync_state`/`price_sync` desde `config` y saca
`storage` de los puentes `entity_migration`, `historical_backfill` y `tenk_extraction`.
[F7.20](f7-historical-core.md) (#130) mueve los periodos acreditados a `identity`
(sin ciclo con `historical_pit`) y lee los registros revisados desde infraestructura.
[F7.21](f7-historical-audits.md) (#131) lleva la descarga paralela y con ritmo de
covers SEC a un caso de uso, saca `requests`/`lxml`/SQL de las auditorías históricas
y retira `historical_data_audit`.
[F7.22](f7-ranking-quality.md) (#132) saca `storage` de `screener_asof` y `data_quality`
y retira cuatro alias pequeños; `rotation_policy` queda por la huella de `rotation_experiment`.
[F7.23](f7-research-ledgers.md) (#133) lleva los registros de experimentos y de
validación ciega a infraestructura; [ADR 0005](../adr/0005-legacy-config-path.md) permite
sustituir `storage` por `config` cuando solo se usaba para la ruta de la base.
Su segunda entrega pasa a `gabi_cli research` las órdenes de las validaciones
#33/#35 y de la viabilidad #44, y deja `smallmid_test` (preregistro en curso).
[F7.24](f7-backtest-inputs.md) (#132) pasa los backtests V1/V2 a casos de uso con
entradas explícitas (`BacktestMarket`) y reglas puras en `domain/portfolio/backtest`;
las fachadas conservan los nombres que parchean los motores congelados.
[F7.25](f7-retire-source-facades.md) (#90) retira `price_sync`, `macro` e `insider`:
`data_fetch`, `data_quality` e `history_refresh` usan directamente sus almacenes y
proveedores, y los respaldos del worker comparten la composición del bootstrap.
[F7.26](f7-retire-blind-validation.md) retira `blind_validation`: reglas al dominio, flujo
al caso de uso `BlindLedger` y los nombres públicos en un adaptador de `infrastructure/legacy`.
[F7.27](f7-identity-audit-command.md) pasa `historical_identity_audit` a
`gabi_cli research identity-audit` (ADR 0002), con sus bucles en aplicación y sus reglas en dominio.
[F7.28](f7-history-refresh-command.md) pasa `history_refresh` a `gabi_cli research history-refresh`,
con su orden de pasos en un caso de uso y sus reglas en dominio.
[F7.29](f7-retire-sync-state.md) retira `sync_state`: el marcapasos único y los reintentos pasan a
`infrastructure/providers/source_retry`, y los checkpoints se leen de `OperationSyncEvents`.
[F7.30](f7-retire-data-fetch.md) retira `data_fetch`: reglas de Yahoo al dominio, refrescos a
`application/market/market_downloads` y descargas por lotes y `refresh_data` en un puente de `infrastructure/legacy`.
[F7.31](f7-sec-history-command.md) pasa `sec_history` a `gabi_cli research sec-history` y la descarga
fijada del archivo SEC a `infrastructure/storage/sec_archive_download.download_pinned`.
[F7.32](f7-retire-data-quality.md) pasa `data_quality` a un puente de `infrastructure/legacy`;
`multifactor_backtest` usa la calidad del ranking del dominio.
[F7.33](f7-retire-app-mode.md) retira `app_mode`: la referencia congelada se lee de
`domain.market.model_policy` y el estado del modelo de `ModelQueries`. Con ella, `pending` queda vacío.

## Responsabilidades y entregas

Cada grupo puede requerir dividir un módulo que hoy mezcla responsabilidades; la
tabla indica destinos, no un movimiento ciego de archivos enteros.

| Grupo histórico representativo | Destino de responsabilidades | Fase / comprobación |
| --- | --- | --- |
| `metrics`, `scoring`, `technicals`, `risk`, `valuation_expectations` | Dominio Mercado; entradas explícitas y determinismo | F2/F3: ranking/ficha y fixtures incompletas |
| `screener`, `evidence_confidence` (`data_quality`, `app_mode` retirados) | Casos de uso Mercado/Administración; reglas puras al dominio; lecturas al adaptador | F2: consulta sin red/escritura; Investor/Research por backend |
| `storage`, `entity_master`, `entity_migration`, `identity` (`sync_state` retirado) | SQL al adaptador; política de identidad al dominio | F2/F4: alias, duplicidad de clases, lotes y cambios aditivos |
| `universe`, `edgar`, `academic_factors`, `estimates`, `historical_*`, `sec_*` (`data_fetch`, `macro`, `insider`, `sec_history` retirados) | Proveedores/archivos en infraestructura; actualización en aplicación | F4/F5/F6: caché ausente no inicia descargas; rate limits y checkpoints |
| `periodic_tasks` (`edgar_sync`, `price_sync`, `history_refresh` retirados) | Casos de uso compartidos, adaptadores CLI y worker persistente | F4: continuidad sin navegador, idempotencia y reinicio |
| `capital_allocation`, `rotation_policy`, `broker_costs`, `tax_drag`, `portfolio_metrics` | Dominio Cartera; coordinación de lecturas/escrituras en aplicación | F5: selección, costes y rentabilidades idénticos |
| `decision_engine`, `sim_portfolios`, `signal_monitor`, `evaluation`, `live_ledger` | Aplicación por capacidad y persistencia específica | F5: operaciones, ledger y contratos sin cambios de interpretación |
| `research_lab`, `blind_validation`, `factor_lab`, `portfolio_lab`, auditorías/backtests/experimentos | Dominio de cálculos; casos de uso Investigación; jobs y artefactos en infraestructura | F6: protocolos, hashes, reservas, resultados y exportaciones |
| Helpers `*_ui`, `ui_helpers` y `app/pages` | Retirados en F6; presentación React y metadatos de contrato (`domain/market/metric_info.py`) | F6: hecho tras verificar la equivalencia por flujo |
| `config`, `workspace` y bootstrap de `gabi` | Compatibilidad histórica preservada; settings explícitos para código nuevo | Todas: raíz estable, datos compartidos y cero efectos de importación |

El listado completo de archivos/imports heredados está en
[architecture-legacy.json](../../.github/architecture-legacy.json); las dependencias
publicadas congeladas, en [legacy-engine-hashes.json](../../backend/legacy-engine-hashes.json).
Qué módulos planos se quedan para siempre, por qué y el criterio de cierre de #90/#91
están en el [inventario de compatibilidad](compatibility-inventory.md)
([architecture-compatibility.json](../../.github/architecture-compatibility.json), ADR 0006).
Los archivos no destacados en la tabla siguen el grupo de su flujo y las mismas
reglas. No quedan fuera de la guarda por no aparecer en un ejemplo.

## Criterio de finalización por flujo

Un flujo migra cuando tiene caso de uso compartido, adaptadores sin fórmulas,
contrato explícito, pruebas de paridad y efectos, documentación de invalidación
y medición si cambió acceso a datos. Sus consumidores dejan de importar I/O/cálculo
plano directamente. Los módulos sin consumidores pueden retirarse después de
comprobar referencias archivadas y podar el baseline. La compatibilidad congelada
permanece documentada hasta decidir explícitamente una nueva versión.

Cerrar F6 no significa fingir que no existe ninguna excepción: el código publicado
conservado se identifica y queda accesible solo mediante sus puentes. La retirada
de Streamlit se hizo tras verificar todos los flujos del inventario F0 y el arranque local
([auditoría F6](f6-research.md)).
