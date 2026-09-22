# Revisión de issues — 2026-09-21

Contraste de los 17 issues de `juavepui/GABI` con el checkout `152ebf7`,
sus tests y la base local. Todos los issues carecían de comentarios al
consultarlos. «Cerrado» describe GitHub; no implica que desaparezcan las
limitaciones documentadas ni que exista validación económica prospectiva.
Esta revisión no cambia el estado de los issues en GitHub.

Actualización 2026-09-22: el trabajo del #12 continúa en el
[informe retrospectivo PBO/DSR](overfitting-audit/README.md), con matriz
36×24, registro de todas las series y alcance pendiente explícito. La tabla
inferior conserva el estado de la revisión del 21 de septiembre.

Actualización adicional 2026-09-22: el #13 cuenta con
[análisis temporal FF5+Momentum](factor-stability/README.md), mitades,
51 ventanas móviles HAC, atribución por episodios/años y exclusión de episodios.
No acredita estabilidad de las permutaciones o perturbaciones de pesos
históricas cuyos inputs completos faltan. No se ha cambiado el estado de GitHub.

Actualización adicional 2026-09-22: el #15 incorpora
[VaR/Expected Shortfall y momentos](tail-risk.md), integración V1/V2,
Portfolio Lab y Research Lab, y cálculo sobre las 24 series recuperadas.
Con 36 trimestres, el 99% queda explícitamente por debajo de la resolución
muestral. La tabla original de abajo conserva el estado del 21 de septiembre.

Actualización adicional 2026-09-22: el #16 incorpora
[benchmarks ajustados por beta y factores](factor-benchmark/README.md),
atribución retrospectiva y estimación expansiva con embargo, curvas comparables,
interfaz y artefactos reproducibles. No se modifica el estado del issue en GitHub.

| Issue | Estado en GitHub | Evidencia local y alcance |
|---|---|---|
| [#1 Calidad y trazabilidad](https://github.com/juavepui/GABI/issues/1) | Cerrado | `data_quality.py`, página Salud de Datos, avisos en ranking/screener/decisiones y `data_fingerprint` en Research Lab. Tests de cobertura, fechas y huellas. Las limitaciones estructurales siguen visibles. |
| [#2 Identidad persistente](https://github.com/juavepui/GABI/issues/2) | Cerrado | `identity.py`, `entity_migration.py`, observaciones atribuidas e integración V1/V2. Tests de alias, reciclaje y migración. La base principal tiene **0 alias**: la infraestructura está entregada, pero la migración y acreditación histórica no están completadas. Ver `entity-identity.md` y `identity-coverage.json`. |
| [#3 Signal Monitor](https://github.com/juavepui/GABI/issues/3) | Cerrado | Comparación de Top-N, rank, score, confidence y sector, persistencia sin duplicados, interfaz `Notifier` y página propia. No hay un evento específico de cambio de `entity_id` ni de elegibilidad por filtro; un cambio de sector no acredita por sí solo un cambio de identidad. |
| [#4 Filings](https://github.com/juavepui/GABI/issues/4) | Cerrado | `filing_tracker.py`, comparación numérica por accession de 10-K/10-Q, integración Ficha/Signal Monitor y tests. La comparación textual permanece fuera de esta primera entrega. |
| [#5 Investor/Research](https://github.com/juavepui/GABI/issues/5) | Cerrado | `app_mode.py`, navegación y bloqueo de pesos, avisos experimentales y tests. Matiz pendiente: `model_status()` devuelve `VALIDATED` por coincidencia de pesos; eso no demuestra validación estadística. `LIVE_FORWARD` se deriva de experimentos de Research Lab, no del registro de validaciones ciegas activas. |
| [#6 Reproducibilidad](https://github.com/juavepui/GABI/issues/6) | Cerrado | `pyproject.toml`, `uv.lock`, CI con lint/mypy/import/compile/pytest, versión de Python y huella de entorno en experimentos, tests de migraciones y documentación de uv. |
| [#7 Calendario](https://github.com/juavepui/GABI/issues/7) | Cerrado | `events_calendar.py`, earnings/dividendos, distinción estimado/confirmado, sorpresa/reacción e integración en Screener/Ficha/Signal Monitor. Hay tests sin red. El calendario macro propuesto no está incluido en este módulo. |
| [#8 Estimaciones](https://github.com/juavepui/GABI/issues/8) | Cerrado | `estimates.py`, snapshots fechados, revisiones, evaluación e integración experimental Ficha/Factor Lab. Sin reconstrucción retroactiva ni incorporación al Composite. `estimates-data.md` deja la validación pendiente de acumular capturas suficientes. |
| [#9 Roadmap P2/P3](https://github.com/juavepui/GABI/issues/9) | Cerrado | Agrupa #1–#8; las entregas anteriores cubren la base del roadmap, con los límites indicados. |
| [#10 Prueba ciega](https://github.com/juavepui/GABI/issues/10) | Cerrado | Existe una validación local bloqueada, Top-20 trimestral, desde 2026-09-21 hasta 2029-09-21, con un rebalanceo registrado. Se comprobó metadato y recuento, sin revelar retornos ni romper el sello. |
| [#11 HAC](https://github.com/juavepui/GABI/issues/11) | Abierto | Antes de esta entrega, inferencia homocedástica. Esta implementación añade Newey-West, comparación OLS, metadatos, UI y tests. Ver `academic-factors-hac.md`. |
| [#12 Auditoría PBO/DSR](https://github.com/juavepui/GABI/issues/12) | Abierto | El commit `152ebf7` y el experimento local #10 ya documentan ocho configuraciones con N=100, DSR≈0,83 y PBO≈0,40. Es parcial: no incluye filtro SMA200 ni variaciones de pesos. El estado abierto no significa ausencia de trabajo. |
| [#13 Regímenes](https://github.com/juavepui/GABI/issues/13) | Abierto | No hay análisis de estabilidad temporal de alfa/betas en `academic_factors.py`; HAC no lo sustituye. |
| [#14 Fiscalidad](https://github.com/juavepui/GABI/issues/14) | Abierto | No hay contabilidad fiscal del backtest; los costes de ejecución no cubren esta cuestión. |
| [#15 Riesgo de cola](https://github.com/juavepui/GABI/issues/15) | Abierto | `portfolio_metrics.py` no implementa VaR/CVaR ni momentos de cola como métricas de cartera. Los momentos usados para DSR no equivalen a esa funcionalidad. |
| [#16 Benchmark por beta/factor](https://github.com/juavepui/GABI/issues/16) | Abierto | Hay SPY, universo equiponderado y regresión de factores, pero no una curva de benchmark ajustada por beta/factores. |
| [#17 Segundo roadmap](https://github.com/juavepui/GABI/issues/17) | Abierto | Agrupa #10–#16. El texto inicial ya no refleja el registro de la prueba ciega ni la auditoría parcial PBO/DSR. |

Las observaciones sobre #2, #3, #5 y #7 son límites de alcance encontrados
en la revisión, no correcciones incluidas silenciosamente en el cambio HAC.
