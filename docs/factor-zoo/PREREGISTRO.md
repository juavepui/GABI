# STAT-5 (#48): preregistro del Factor Zoo

Sellado antes de calcular el resultado de #48. La especificación completa
está en [preregistro.json](preregistro.json), SHA-256
`fdf6e429282e7c70ed9ae5c8ac7997bbdbb39b55d8675324eaef9586f6017e59`.

## Señales fijadas

Se prueban las 13 métricas representativas que puntúan en `SCORE_METRICS`.
Los múltiplos y ratios adicionales visibles en la aplicación se excluyen para
evitar que familias obvias voten varias veces. Se usa el percentil `_pct` del
ranking histórico, ya orientado y normalizado por sector cuando hay datos.

| Familia | Métricas | Signo crudo esperado |
| --- | --- | --- |
| Value | `pe`, `pb`, `ev_ebitda` | Menor es mejor |
| Quality | `roic`, `operating_margin`, `revenue_cagr_3y`, `fcf_cagr_3y` | Mayor es mejor |
| Momentum | `momentum_12m`, `rel_strength_6m`, `price_vs_sma200` | Mayor es mejor |
| Risk | `debt_to_equity`, `volatility`, `max_drawdown` | Menor para deuda/volatilidad; mayor para drawdown (menos negativo) |

## Datos y análisis fijados

Los mismos 57 rebalanceos, elegibles y retornos futuros de #40. Para cada
señal se calcula el Rank IC de Spearman trimestral entre `_pct` y retorno.
Se excluyen parejas sin dato; se requieren al menos 30 empresas por trimestre
y 30 trimestres para inferencia. No se imputan datos. La hipótesis unilateral
es IC medio > 0, con t Newey-West Bartlett de tres retardos. Los huecos
conservan su posición en el calendario; no se comprime la serie. Se corrigen
las **13** pruebas principales por Holm con `alpha=0,05`.

Se publican ICIR (media/desviación temporal), proporción de IC positivo,
retornos equiponderados por quintil y decil, spreads extremos y pendiente
Fama-MacBeth con controles de sector y log-capitalización cuando haya al menos
30 trimestres. Esos análisis son descriptivos: no eligen señales. También se
informan las ventanas fijas 2011–15, 2016–20 y 2021–25, IC por sector con
al menos 30 empresas por trimestre, IC por tercil de tamaño y correlación de
Spearman media entre señales.

Clasificación fijada: `sin_evidencia` si IC medio <= 0 o no evaluable;
`indicio` si positivo pero Holm >= 0,05; `requiere_OOS` si Holm < 0,05 pero
menos de dos ventanas o terciles de tamaño tienen IC positivo; y
`robusta_retrospectivamente` si Holm < 0,05 y al menos dos ventanas y dos
terciles son positivos. **Todas** las categorías son retrospectivas y
requieren validación independiente para cambiar el Composite. No se
seleccionará ningún factor por CAGR del Top-N.
