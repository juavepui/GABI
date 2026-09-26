# Métricas de mercado del Composite: ventanas y precios (issue #31)

Las seis métricas de Momentum y Risk que puntúan en el Composite
(`scoring.SCORE_METRICS`) se calculan con `technicals.compute_technicals` y
`risk.compute_risk_metrics`. El #31 no cambió ninguna fórmula: en 2010–2015 el
único problema era la falta de precios acreditados, resuelta en #28/#32.
`debt_to_equity` también está en Risk, pero es fundamental y se trata en #30.

## Definiciones vigentes

Todas usan `adj_close` (ajustado por splits y dividendos) si la serie lo tiene
completo, y si no `close`, sin mezclar ambos en la misma serie. Las ventanas se
cuentan en **observaciones** (sesiones con precio), no en días naturales.

| Métrica | Fórmula | Ventana | Ausente si |
| --- | --- | --- | --- |
| `momentum_12m` | último / precio de hace 252 observaciones − 1 | 253 cierres (252 retornos) | ≤ 252 cierres o precio inicial nulo |
| `rel_strength_6m` | momentum 6m de la acción − momentum 6m de SPY | 127 cierres de cada serie | alguna serie ≤ 126 cierres, o **las ventanas no empiezan y terminan en las mismas fechas** (nuevo en #31) |
| `price_vs_sma200` | último / media de las 200 últimas observaciones − 1 | 200 cierres | < 200 cierres |
| `volatility` | desviación típica de retornos diarios × √252 | **toda la serie recibida** | sin retornos |
| `max_drawdown` | mínimo de precio / máximo previo − 1 | **toda la serie recibida** | sin precios |

`price` (el precio mostrado) sigue siendo el cierre nominal.

**Sin información futura.** El ranking trunca la serie en la fecha evaluada
(`screener_asof._price_history_as_of`). En 2010–2015 además solo lee la serie
acreditada de la entidad (`historical_pit.ranking_series`): una fuente por
serie, sin rellenar sesiones, sin mezclar otra entidad que use el mismo ticker
y solo si la ventana de la última fecha auditada fue acreditada.

## Cobertura medida

Porcentaje de empresas con precio acreditado que tienen cada métrica, sobre los
rankings congelados de la [validación 2010–2015](historical-validation-2010-2015/README.md)
y de la [auditoría 2016+](full-universe-audit/README.md):

| Métrica | 2010–2011T1 | 2011T3–2013 | 2014–2015 | 2016–2017 | 2020–2025 |
| --- | ---: | ---: | ---: | ---: | ---: |
| `momentum_12m` | 100 | 100 | 100 | 80 | 92 |
| `rel_strength_6m` | 100 | 100 | 100 | 81 | 92 |
| `price_vs_sma200` | 100 | 100 | 100 | 80 | 92 |
| `volatility` | 100 | 100 | 100 | 81 | 92 |
| `max_drawdown` | 100 | 100 | 100 | 81 | 92 |

La menor cobertura de 2016+ viene del camino por ticker y se trata en #34.

En la fuerza relativa se comprobó con datos reales que ninguna ventana estaba
desalineada (2012-12-31, 2014-06-30, 2017-07-03, 2020-07-02 y 2024-07-02, entre
403 y 486 empresas por fecha). La protección de fechas no cambia ningún
resultado: los rankings de 2016-06-30 y 2018-06-29 son idénticos (mismo hash)
antes y después del cambio.

## Hallazgo: la volatilidad y el drawdown no tienen ventana fija

`volatility` y `max_drawdown` se calculan sobre **toda la historia** que reciben,
así que su horizonte depende de cuánto historial hay:

| Fecha de ranking | Años de historia usados (p10 / mediana / p90 / máx.) | Origen de la serie |
| --- | --- | --- |
| 2010-07-02 | 1,3 / 1,3 / 1,3 / 1,3 | intervalo acreditado (desde 2009) |
| 2012-12-31 | 2,5 / 3,8 / 3,8 / 3,8 | intervalo acreditado |
| 2015-06-30 | 2,5 / 6,2 / 6,2 / 6,2 | intervalo acreditado |
| 2017-07-03 | 11,3 / 32,2 / 45,1 / 55,5 | caché por ticker |
| 2024-07-02 | 12,1 / 32,9 / 51,4 / 62,5 | caché por ticker |

En 2016–2025 el «riesgo» de GABI mide sobre todo el **drawdown de toda la vida
cotizada** de la empresa (dominado por 2000–2002 y 2008), no su riesgo reciente,
y penaliza en la práctica a las empresas con más historia. En 2010–2015 esas dos
métricas miden otra cosa, porque no hay datos acreditados anteriores a 2009. La
volatilidad y el drawdown pesan en el 10 % de Risk, y dentro del percentil de
cada fecha el efecto está en la **dispersión de horizontes entre empresas**.

Cambiarlo es una decisión de modelo que altera los resultados de 2016+, y el
#31 prohíbe decidirlo en silencio. Queda planteado en el #37: fijar una ventana
común (por ejemplo, 3 años) y revalidarla con protocolo preregistrado, o
mantener la semántica actual documentando la diferencia entre periodos.
