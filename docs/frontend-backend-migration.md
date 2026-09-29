# Separación local de GABI — inventario y plan F0

Épica [#61](https://github.com/juavepui/GABI/issues/61). Inventario realizado sobre
`7821a795e9e44e0ae5b775584dee70b4a17ad995` y preparación de
[#62](https://github.com/juavepui/GABI/issues/62). La separación física de F1 se
describe en [su entrega y compatibilidad](backend-layout-compatibility.md).
La API y el cliente React se implementan después; Streamlit sigue operativo.

Las decisiones vigentes de capas, dependencias, datos, rendimiento y evolución
del código antiguo están en [arquitectura](architecture.md). Cada fase aplica
esas reglas y conserva las guardas de arquitectura en CI.

El destino es Python + FastAPI y React + TypeScript + Vite + React Router +
shadcn/ui. GABI seguirá siendo local y gratuito, con SQLite y el directorio
`data/` compartido en la raíz. Se migrará por flujos comprobables, conservando
Streamlit hasta terminar la verificación de equivalencia.

## Fases y dependencias

| Fase | Entrega | Dependencia |
| --- | --- | --- |
| [F0 · #62](https://github.com/juavepui/GABI/issues/62) | Inventario, límites y etiquetas de evidencia | Ninguna |
| [F1 · #63](https://github.com/juavepui/GABI/issues/63) | Carpetas, empaquetado y compatibilidad de rutas | #62 |
| [F2 · #64](https://github.com/juavepui/GABI/issues/64) | API de Screener, ficha, datos y modelo | #63 |
| [F3 · #65](https://github.com/juavepui/GABI/issues/65) | Cliente visual y primer flujo Screener → ficha | #64 |
| [F4 · #66](https://github.com/juavepui/GABI/issues/66) | Jobs persistentes y Administración | #64, #65 |
| [F5 · #67](https://github.com/juavepui/GABI/issues/67) | Resto de Cartera y Mercado | #65, #66 |
| [F6 · #68](https://github.com/juavepui/GABI/issues/68) | Investigación, distribución local y retirada de Streamlit | #67 |

La #60 sigue abierta porque no hay una estrategia demostrada que cumpla el
objetivo. Su [registro de búsquedas](search-ledger/README.md) y sus limitaciones
se conservan durante la migración. La evidencia financiera y la migración tienen
criterios de aceptación distintos; los flujos de investigación pueden avanzar
sin declarar éxito de la estrategia.

## Mapa completo de las 17 páginas

Los módulos enumerados son los servicios principales que reutilizar; las
dependencias transitivas se conservan con el paquete. Los adaptadores UI nunca
deben duplicar fórmulas de scoring, costes o riesgo.

| Página actual (`app/pages/`) | Sección nueva | Servicios Python principales | Efectos que debe conservar el contrato | Fase |
| --- | --- | --- | --- | --- |
| `0_Mi_Cartera.py` | Cartera | `screener`, `simple_portfolio`, `app_mode` | Lectura de ranking y reglas; capital/posiciones del usuario | F5 |
| `1_Screener.py` | Mercado | `screener`, `data_quality`, `evaluation`, `live_ledger` | Ranking, cobertura y filtros; capturas explícitas del ledger | F3 |
| `2_Ficha_Empresa.py` | Mercado | `scoring`, `storage`, `estimates`, `events_calendar`, `filing_tracker`, `insider`, `ai_prompt` | Métricas, precios, filings y enlaces; separar consultas externas de caché | F3 |
| `3_Configuracion.py` | Administración | `config`, `screener` | Pesos y claves locales; actualización y reintentos como jobs | F4 |
| `4_Diario_Inversion.py` | Cartera | `journal`, `storage` | Lectura/escritura de tesis y anotaciones existentes | F5 |
| `5_Panel_Macro.py` | Mercado | `macro`, `config` | Lectura de indicadores, caché y refresco de fuentes separado | F5 |
| `6_Comparar_Empresas.py` | Mercado | `screener`, `config` | Comparación de 2–5 empresas, unidades iguales a Screener | F5 |
| `7_Aprender.py` | Cartera / ayuda contextual | `scoring`, diccionario de métricas | Contenido y explicaciones sin cálculos financieros nuevos | F5 |
| `8_Ranking_Historico.py` | Investigación | `screener_asof`, `multifactor_backtest`, `portfolio_backtest`, `portfolio_metrics`, `factor_benchmark`, `tax_drag` | Backtests y comparaciones largos como jobs; registro de resultados | F6 |
| `9_Decisiones.py` | Cartera | `decision_engine`, `screener`, `data_quality`, `storage` | Reglas experimentales y decisiones registradas; no envía órdenes | F5 |
| `10_Carteras_Simuladas.py` | Cartera | `sim_portfolios`, `storage`, `data_fetch` | Simulaciones, operaciones y posiciones persistentes; cálculo largo como job | F5 |
| `11_Research_Lab.py` | Investigación | `research_lab`, `overfitting_audit`, `stats_rigor`, `block_bootstrap`, `factor_stability` | Protocolos, ensayos, artefactos, fallos y exportaciones | F6 |
| `12_Factor_Lab.py` | Investigación | `factor_lab`, `estimates`, `factor_sector_stability` | Análisis de factores y ventanas sin promoción automática | F6 |
| `13_Blind_Validation.py` | Investigación | `blind_validation`, `periodic_tasks` | Crear/registrar estudios; sellos y acceso a resultados regulado por protocolo | F6 |
| `14_Portfolio_Lab.py` | Investigación | `portfolio_lab`, `tail_risk` | Construcciones alternativas y riesgo; experimentos explícitos | F6 |
| `15_Salud_Datos.py` | Administración | `data_quality`, `historical_archive`, `identity`, `storage` | Frescura, cobertura, identidad y archivo; auditorías largas como jobs | F4 |
| `16_Signal_Monitor.py` | Mercado | `signal_monitor`, `filing_tracker`, `events_calendar`, `evaluation` | Cambios de señal/eventos y consultas externas explícitas | F5 |

La portada y el selector Investor/Research no son una página adicional del
inventario: se convierten en elementos comunes de navegación/estado. La raíz del
cliente ofrecerá un resumen de datos, modelo y tareas pendientes. En cada sección
se conservarán las restricciones Investor/Research en el servidor.

Hay nueve helpers de presentación dentro de `src/gabi`: `ui_helpers`,
`evidence_ui`, `block_bootstrap_ui`, `factor_benchmark_ui`, `factor_sector_ui`,
`factor_stability_ui`, `live_ledger_ui`, `rank_stability_ui` y `tail_risk_ui`.
F1 puede mantenerlos por compatibilidad; F6 retira su dependencia Streamlit
después de migrar sus consumidores. Las etiquetas de métricas/unidades que se
reutilicen pasan a un contrato compartido, sin transportar objetos Streamlit,
DataFrames o HTML por HTTP.

## Contratos iniciales que se comprobarán en F2/F3

La API propuesta usa `/api/v1`. Salud del proceso, estado del modelo, estado de
los datos, ranking y ficha deben poder consultarse sin iniciar descargas o
backtests. La función actual `get_universe` puede refrescar fuentes; el servicio
HTTP deberá distinguir leer caché de pedir una actualización.

| Información | Representación y regla |
| --- | --- |
| Empresa | Símbolo, CIK/identidad cuando esté acreditada y etiqueta visible; un ticker no se considera identidad permanente |
| Ranking | Orden, score, bloques, cobertura, universo, pesos, modo y fecha de cálculo; filtros/ordenación definidos por backend |
| Métrica | Nombre, valor finito o `null`, unidad, fecha y procedencia; fracciones no se convierten dos veces a porcentajes |
| Precios/rentabilidades | USD, ajustado/bruto declarado; costes/dividendos/periodo explícitos, sin llamar CAGR a periodos discontinuos |
| Datos | Fecha de señal/cálculo/última actualización, cobertura, ausencia y obsolescencia diferenciadas |
| Modelo/evidencia | Identificador, reglas/configuración, `FROZEN`/`LIVE_FORWARD`/`EXPERIMENTAL`, tipo de evidencia y validación pendiente |
| Error | Código estable y mensaje útil; sin secretos, trazas internas ni `NaN`/`Infinity` en JSON |
| Job | Identificador, tipo, estado persistente, progreso, timestamps, fallos y referencia al resultado completo |

Los nombres finales de endpoints y modelos se fijan al implementar F2 y se
publican en OpenAPI. El cliente TypeScript se obtiene de ese contrato. Una
consulta lenta debe apoyarse en resultados cacheados o en un job explícito.

## Rutas y evidencias que condicionan el traslado

| Dependencia actual | Qué debe resolver F1 |
| --- | --- |
| `config.BASE_DIR = Path(__file__).resolve().parents[2]` | Raíz estable de repositorio/datos al mover el paquete; configuración explícita, independiente del cwd |
| `DATA_DIR`, `DB_PATH`, caches y ficheros de claves | Seguir usando `GABI/data`; no duplicar/mover los aproximadamente 83,2 GB declarados por el usuario; no enviar claves al cliente |
| Imports manuales `parents[1]/src` y `parents[2]/src` en `app/` | Importar el backend instalado y comprobar las 17 páginas de transición |
| `pyproject.toml`, `uv.lock`, wheel `src/gabi` y `tests/` | Proyecto Python en backend, lock actualizado, instalación editable y ejecución desde raíz/backend |
| `frozen_research_ci.ROOT/FROZEN` y `.github/mypy-baseline.json` | Traducir rutas con control explícito; conservar hashes exactos de los tres motores y los 25 diagnósticos antiguos |
| Manifiestos con claves `src/gabi/...` y `data/...` | Resolver aliases históricos a rutas físicas nuevas sin modificar el JSON sellado ni sus huellas |
| Hashes de código/inputs de los motores de investigación | Mantener bytes normalizados y semántica; una adaptación necesaria se versiona y no reesella evidencia anterior |
| `live_ledger.capture_config` y git diff sobre `src/gabi` | Capturar el código trasladado y conservar lectura de registros anteriores, sin afirmar identidad si cambió código |
| Salidas `BASE_DIR/docs` y snapshots bajo `DATA_DIR` | Mantener referencias verificables, lectura `mode=ro`, resultados publicados y separación de cachés operativas |
| `scripts/programar_tareas.ps1` y CLI `gabi.periodic_tasks` | Resolver intérprete/working directory reales; no reinstalar tareas del usuario silenciosamente |
| `.github/workflows/ci.yml` | Working directories y checks Python/TypeScript; mantener verificación de motores y registro de búsquedas |

Los motores `tail_effect_test`, `factor_zoo` y `placebo_engine` tienen una guarda
explícita de SHA-256 en CI. `strategy_discovery`, `repurchase_cash_strategy`,
auditorías de inputs, SIC y demás estudios publicados también guardan hashes de
código/datos en sus protocolos. Mover archivos no autoriza cambiar su contenido
ni el significado de rutas guardadas. Si el diseño de compatibilidad no permite
verificar un informe antiguo, F1 no cumple su aceptación.

## Convivencia, comprobación y vuelta atrás

F1 cambia estructura con Streamlit todavía operativo; F2 añade un cliente HTTP
de los mismos servicios; F3 sustituye Screener/ficha. Cada fase mantiene un
arranque documentado y CI verde antes de pasar a la siguiente. Las primeras
entregas se comprueban con datos de prueba aislados y resultados cacheados,
comparando identidad, elegibilidad, score, cobertura, orden, fechas, costes y
unidades con el servicio existente. F4 añade pruebas de persistencia,
concurrencia y reinicio; F5/F6 prueban también las escrituras existentes y las
restricciones de reservas por HTTP.

Durante F1–F5 se vuelve al cliente Streamlit sobre la misma base y servicios.
Cualquier cambio de esquema debe ser aditivo y con procedimiento de copia de
seguridad/recuperación antes de aplicarlo; retirar columnas o convertir datos
irreversiblemente queda fuera de una mera migración de interfaz. Al cerrar F6,
FastAPI servirá el build de Vite bajo un origen local y el arranque también
incluirá el worker necesario. No se necesita una nube ni un servicio de pago.

F0 corrige la portada, ayudas y estado del modelo: coincidir con los pesos
congelados produce `FROZEN`, nunca `VALIDATED` por ese solo motivo.
`LIVE_FORWARD` indica seguimiento en curso y no éxito estadístico. Los pesos,
selecciones, retornos y reservas no cambian con esa corrección.
