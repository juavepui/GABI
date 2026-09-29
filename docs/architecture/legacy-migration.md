# Migración de los módulos existentes

Fuente normativa: [arquitectura de GABI](../architecture.md). Este plan aplica sus
reglas al código antiguo sin modificar de golpe cálculos o artefactos publicados.

## Cómo evolucionar un módulo antiguo

1. Localizar sus consumidores, dependencias y archivos sellados. Capturar una
   fixture aislada y comprobar el comportamiento vigente: identidad, elegibilidad,
   orden, score, costes, fechas, null y unidades según corresponda.
2. Separar cálculo puro, coordinación e I/O en las capas previstas. Crear el caso
   de uso mínimo y su puerto concreto. Una ruta nueva no llama directamente al
   módulo plano: usa el caso de uso y un puente `infrastructure/legacy` si hace falta.
3. Migrar un flujo completo. Streamlit y API usan el mismo caso de uso; el nombre
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

## Responsabilidades y entregas

Cada grupo puede requerir dividir un módulo que hoy mezcla responsabilidades; la
tabla indica destinos, no un movimiento ciego de archivos enteros.

| Grupo actual representativo | Destino de responsabilidades | Fase / comprobación |
| --- | --- | --- |
| `metrics`, `scoring`, `technicals`, `risk`, `valuation_expectations` | Dominio Mercado; entradas explícitas y determinismo | F2/F3: ranking/ficha y fixtures incompletas |
| `screener`, `data_quality`, `evidence_confidence`, `app_mode` | Casos de uso Mercado/Administración; reglas puras al dominio; lecturas al adaptador | F2: consulta sin red/escritura; Investor/Research por backend |
| `storage`, `entity_master`, `entity_migration`, `identity`, `sync_state` | SQL al adaptador; política de identidad al dominio | F2/F4: alias, duplicidad de clases, lotes y cambios aditivos |
| `data_fetch`, `universe`, `edgar`, `macro`, `academic_factors`, `insider`, `estimates`, `historical_*`, `sec_*` | Proveedores/archivos en infraestructura; actualización en aplicación | F4/F5/F6: caché ausente no inicia descargas; rate limits y checkpoints |
| `periodic_tasks`, `price_sync`, `edgar_sync`, `history_refresh` | Casos de uso compartidos, adaptadores CLI y worker persistente | F4: continuidad sin navegador, idempotencia y reinicio |
| `simple_portfolio`, `capital_allocation`, `rotation_policy`, `broker_costs`, `tax_drag`, `portfolio_metrics` | Dominio Cartera; coordinación de lecturas/escrituras en aplicación | F5: selección, costes y rentabilidades idénticos |
| `journal`, `decision_engine`, `sim_portfolios`, `signal_monitor`, `evaluation`, `live_ledger` | Aplicación por capacidad y persistencia específica | F5: operaciones, ledger y contratos sin cambios de interpretación |
| `research_lab`, `blind_validation`, `factor_lab`, `portfolio_lab`, auditorías/backtests/experimentos | Dominio de cálculos; casos de uso Investigación; jobs y artefactos en infraestructura | F6: protocolos, hashes, reservas, resultados y exportaciones |
| Helpers `*_ui`, `ui_helpers` y `app/pages` | Adaptador Streamlit temporal; presentación React y metadatos de contrato | F3/F5/F6: equivalencia por flujo antes de retirar consumidores |
| `config`, `workspace` y bootstrap de `gabi` | Compatibilidad histórica preservada; settings explícitos para código nuevo | Todas: raíz estable, datos compartidos y cero efectos de importación |

El listado completo de archivos/imports heredados está en
[architecture-legacy.json](../../.github/architecture-legacy.json); las dependencias
publicadas congeladas, en [legacy-engine-hashes.json](../../backend/legacy-engine-hashes.json).
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
de Streamlit exige verificar todos los flujos del inventario F0 y el arranque local.
