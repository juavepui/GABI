# Experimento de rotación: control frente a umbrales de 5 y 10 puntos

Ejecutado el 23 de septiembre de 2026. El umbral de 10 puntos mejora ligeramente
el CAGR histórico y reduce costes y rotación; el de 5 puntos reduce costes pero
empeora la rentabilidad. Ninguna variante se ha promovido automáticamente a la
estrategia de producción.

## Protocolo e inputs

Las tres configuraciones estaban especificadas en la conversación antes del
cálculo. [protocol.json](protocol.json) se escribió antes del primer backtest:
Top-20, V2, pesos 30/35/25/10, universo histórico completo por fecha, capital
100.000 USD, comisión 1 USD por operación y spread total 10 pb. Las variantes
solo cambian `rotation_hurdle_points` a 5 y 10. La regla exige una mejora en
puntos del Composite; no estima directamente rentabilidad esperada en dólares.

Se reutilizan los 39 rankings completos y el snapshot de SQLite congelados en
la [auditoría del universo completo](../full-universe-audit/README.md), con sus
hashes comprobados. Fechas de ranking: 2016-01-02 a 2025-07-02; valoración:
2016-01-04 a 2025-10-02. Todos los ensayos completan 39/39 trimestres y 2.452
sesiones. Se comprobaron precios en cada sesión de cada posición mantenida,
sin huecos. El NAV del control reproduce exactamente el publicado anteriormente.

## Resultado completo

| Métrica | Composite actual | Umbral 5 | Umbral 10 |
|---|---:|---:|---:|
| CAGR neto | 21,12% | 20,68% | 21,26% |
| Diferencia de CAGR frente al control | — | −0,44 pp/año | +0,14 pp/año |
| Capital final desde 100.000 USD | 647.145,39 | 624.607,25 | 654.224,85 |
| Diferencia de capital final | — | −22.538,14 | +7.079,47 |
| Máximo drawdown | −38,17% | −36,67% | −35,15% |
| ES 95% diario (pérdida) | 3,023% | 2,996% | 2,997% |
| ES 99% diario (pérdida) | 5,242% | 5,238% | 5,158% |
| Turnover medio por rebalanceo | 74,72% | 51,67% | 38,52% |
| Comisiones acumuladas, USD | 1.048,00 | 951,00 | 895,00 |
| Spread acumulado, USD | 4.608,39 | 3.174,12 | 2.251,27 |
| Coste total observado, USD | 5.656,39 | 4.125,12 | 3.146,27 |
| Sustituciones de empresas (ventas completas) | 268 | 171 | 115 |
| Beta diaria frente a SPY | 1,007 | 1,011 | 1,025 |
| Trimestres mejores / peores / iguales al control | — | 16 / 22 / 1 | 22 / 16 / 1 |

El umbral 10 reduce el turnover un **48,44%** y el coste observado un **44,38%**
(2.510,12 USD menos). El peor drawdown se reduce en **3,03 puntos porcentuales**.
El capital final aumenta un **1,09%** frente al control después de casi diez años.
La mejora de CAGR es pequeña: **0,1353 puntos porcentuales anuales**.

El umbral 5 reduce el turnover un 30,85% y los costes un 27,07%, pero deja un
3,48% menos de capital final. Ahorrar costes no garantiza una mejor selección.

SPY buy-and-hold, con los mismos precios y fechas: CAGR 15,00%, capital final
390.472,43 USD, drawdown −33,72%, ES diario 95/99 de 2,787% / 4,842%.

## Estabilidad temporal

El corte temporal se fijó antes del cálculo. Ambos tramos son retrospectivos,
ya conocidos por el proceso de investigación; no constituyen una prueba futura
ni un holdout históricamente intacto. Se conserva la cartera al cruzar el corte.

| Tramo | Control CAGR | Umbral 5 CAGR | Diferencia | Umbral 10 CAGR | Diferencia |
|---|---:|---:|---:|---:|---:|
| 2016–2020, 20 trimestres | 23,98% | 24,41% | +0,43 pp | 23,56% | −0,42 pp |
| 2021–2025, 19 trimestres | 18,20% | 16,89% | −1,30 pp | 18,89% | +0,69 pp |

La ventaja del umbral 10 cambia de signo entre tramos. En 2021–2025, su
drawdown empeora de −24,69% a −26,09%, y su ES 99% diario pasa de 4,032% a
4,064%. La reducción del peor drawdown de toda la muestra no es uniforme.

Supera al control en 22/39 trimestres (56,4% de esta muestra); ese porcentaje
no estima una probabilidad de éxito futuro. Su diferencia aritmética media de
retorno trimestral es prácticamente cero (−0,00174 puntos porcentuales). El
CAGR, que compone retornos, mide algo distinto de esa media y del alfa de una
regresión. La pequeña mejora no acredita habilidad de selección ni significancia.

## Cálculos, alcance y límites

- El CAGR completo divide el valor final por los 100.000 USD iniciales, incluyendo
  costes de entrada. Los cortes internos usan el NAV previo a la primera sesión
  del tramo; no pierden retornos ni solapan sesiones entre ventanas.
- Turnover es compras más ventas dividido entre patrimonio en cada rebalanceo,
  incluyendo ajustes de peso. Mantener nombres no elimina esos ajustes.
- Coste total es pérdida de patrimonio al ejecutar cada rebalanceo a precios
  constantes: comisión más spread. Los USD son costes observados, no un
  contrafactual del drag compuesto con idénticas posiciones.
- ES es la pérdida media de la peor masa del 5%/1% de retornos diarios,
  incluyendo fracción de la observación frontera, sin anualizar.
- Retornos en USD, con dividendos/splits ajustados, antes de IRPF y conversión
  de divisa, sin liquidación final. Se mantiene la contabilidad original de V2,
  incluida su pequeña caja negativa tras costes y ausencia de coste financiero.
- Persisten los límites de cobertura e identidad de la auditoría original.
  «Universo completo» significa todos los constituyentes enumerados, no que
  todos dispongan de fundamentales elegibles.
- Este experimento mide la política de rotación (#21). Las nuevas métricas de
  persistencia, expectativas y asignación de capital (#19/#20/#22) no alteran
  el ranking y no se les atribuye esta mejora.
- No se ha leído, modificado ni revelado la prueba ciega. El periodo futuro
  está marcado como `not_evaluated`.

Se corrigieron las fechas erróneas, la etiqueta de «futuro» histórico y la
omisión de costes iniciales/spread del arnés de #23 antes de medir resultados.
El cálculo se reanudó tras una discrepancia de resolución de fechas ns/us en
la comprobación del control; los valores y fechas guardados coincidían.

## Artefactos

- [metrics.csv](metrics.csv): todas las métricas, por cartera y tramo.
- [audit.json](audit.json): resultados, comparaciones trimestrales, comprobaciones
  de precios y hashes (también normalizados a LF para portabilidad).
- [quarterly-returns.csv](quarterly-returns.csv): 39 retornos por cartera,
  reconciliados con el capital final.
- `*-nav.csv`, `*-periods.csv`, [trades.csv](trades.csv): curvas, rebalanceos,
  costes y recuentos de sustituciones.

Reproducción: `python -m gabi.rotation_experiment --output <directorio_nuevo>`
con la caché original disponible y sin una base de trabajo previa, o
`--resume` para continuar el mismo protocolo. No se descargan datos nuevos.
Las pruebas de los artefactos públicos no requieren la base privada:
`python -m pytest tests/test_rotation_experiment.py -q`.
