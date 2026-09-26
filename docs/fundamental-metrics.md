# Métricas fundamentales del Composite: fórmulas point-in-time (issue #30)

Las siete métricas de Value y Quality que puntúan en el Composite
(`scoring.SCORE_METRICS`) se calculan con `edgar.compute_edgar_metrics` sobre
los hechos SEC conocidos en la fecha del ranking, combinados con el precio y el
número de acciones de esa fecha en `screener_asof._classic_metrics_as_of`. El
#30 **no cambió ninguna fórmula**: ya funcionaban por CIK y fecha de
presentación desde #29/#32. Se han documentado, se ha hecho determinista la
elección de saldos reexpresados, se han añadido tests y se explica cada ausencia.

## Regla point-in-time

En una fecha `t` solo se usan hechos con `filed_date ≤ t`
(`_facts_dict_from_stored`). Un hecho reexpresado después de `t` no afecta a
`t`. En 2010–2015 los hechos se leen por CIK (`entity_observations`, nunca por
ticker actual) y el precio sale de la serie acreditada de la entidad.

**Valores anuales, no TTM.** Todas las partidas de resultados y flujos son
ejercicios completos de 10-K/10-K/A (duración de 340 a 380 días, incluidos
ejercicios que no cierran en diciembre). Para cada fin de ejercicio se toma la
versión presentada más reciente conocida en `t`. Los saldos de balance son el
cierre del ejercicio en el 10-K; si el mismo cierre aparece como año corriente
y como comparativo reexpresado, gana el presentado más tarde (antes dependía
del orden de lectura). Tras un cierre, el dato nuevo entra cuando se presenta el
10-K, normalmente 2–3 meses después.

## Fórmulas

| Métrica | Fórmula | Ausente si |
| --- | --- | --- |
| PER | capitalización / beneficio neto del último ejercicio | sin precio, sin acciones o beneficio ≤ 0 |
| P/VC | capitalización / patrimonio neto del último cierre | sin precio, sin acciones o patrimonio ≤ 0 |
| EV/EBITDA | (capitalización + deuda a largo plazo − caja) / (resultado operativo + amortizaciones del último ejercicio) | sin precio, sin acciones, sin resultado operativo o amortizaciones, o EBITDA ≤ 0 |
| ROIC | beneficio neto / (patrimonio + deuda a largo plazo) en el último cierre común a las tres partidas | falta alguna, sin cierre común o capital invertido ≤ 0 |
| Margen operativo | resultado operativo / ingresos del último ejercicio | sin ingresos anuales o sin resultado operativo |
| CAGR ingresos 3a | (último / hace tres ejercicios)^(1/3) − 1 | menos de 4 ejercicios, ejercicios no consecutivos (340–380 días entre cierres) o valor inicial o final ≤ 0 |
| CAGR FCF 3a | igual sobre FCF = flujo operativo − \|capex\| | sin flujo operativo o capex, o las mismas condiciones del CAGR |

La capitalización es el cierre negociado de la fecha (se deshacen los splits
posteriores si la fuente es la caché Yahoo) por las acciones en circulación
presentadas hasta esa fecha. Aproximaciones vigentes, documentadas y sin
cambios: el ROIC usa el beneficio neto como NOPAT y solo la deuda a largo plazo;
el EV usa solo deuda a largo plazo y cuenta como cero una deuda o una caja
ausentes (test `test_enterprise_value_treats_missing_debt_or_cash_as_zero_today`).

## Por qué falta una métrica

`screener_asof.fundamental_diagnostics(símbolo, fecha, entity_id=...)` devuelve el
motivo de cada ausencia con las mismas reglas del cálculo; nunca sustituye con
fundamentales actuales. Principales motivos entre los miembros con identidad
acreditada:

| Métrica | 2010-07-02 (486) | 2013-01-02 (491) | 2015-07-02 (494) |
| --- | --- | --- | --- |
| PER calculable | 217 | 372 | 393 |
| — sin acciones / sin precio acreditado / sin beneficio | 85 / 78 / 72 | 9 / 53 / 38 | 10 / 53 / 25 |
| CAGR ingresos calculable | **1** | 372 | 390 |
| — menos de 4 ejercicios / sin ingresos anuales | 272 / 213 | 24 / 91 | 23 / 73 |
| CAGR FCF calculable | **1** | 289 | 301 |
| — sin capex / base ≤ 0 / menos de 4 ejercicios | 97 / – / 232 | 116 / 50 / 22 | 106 / 50 / 24 |
| ROIC calculable | 156 | 350 | 384 |
| Margen operativo calculable | 196 | 318 | 338 |
| EV/EBITDA calculable | 126 | 271 | 276 |

- **2010**: muchas empresas todavía no habían presentado un 10-K en XBRL (las
  medianas empezaron en 2010–2011) y el primer 10-K XBRL de las grandes es el del
  ejercicio 2009. Un CAGR a 3 años necesita 4 cierres, así que en 2010 no existe
  para casi nadie. Recuperarlo exigiría extraer los ejercicios 2006–2008 de 10-K
  en texto; no se hace (límite documentado).
- **Estructural en todos los periodos**: bancos y aseguradoras no reportan las
  etiquetas de ingresos, resultado operativo ni capex que usa GABI, y unas 50
  empresas por fecha tienen FCF inicial o final ≤ 0. Ocurre igual en 2016+.

## Inconsistencia detectada: ejercicios mezclados → #38

Cada componente toma su **propio** último valor anual. Si una etiqueta deja de
reportarse, el ratio mezcla ejercicios. Por ejemplo, el margen operativo divide
el resultado operativo de 2012 entre los ingresos de 2014 (test
`test_mixed_fiscal_years_are_current_behaviour_and_documented`). Medido entre los
miembros con ingresos anuales (más de 45 días de diferencia con el último
ejercicio de ingresos):

| Fecha | Empresas | Beneficio más antiguo | Deuda LP más antigua | Resultado operativo | Amortización | Patrimonio |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2013-01-02 | 400 | 23 | 28 | 5 | 7 | 12 |
| 2015-07-02 | 421 | 34 | 72 | 13 | 22 | 7 |
| 2018-07-02 | 364 | 28 | 66 | 13 | 15 | 18 |
| 2023-07-02 | 481 | 35 | 116 | 22 | 36 | 19 |

Afecta también a 2016–2025. Alinear los ejercicios cambia el Composite, así que
no se ha hecho aquí: queda como decisión en #38.

## Tests

`tests/test_fundamental_metrics_pit.py` (ejercicio que cierra en junio, CAGR sin
cuatro ejercicios o con huecos o bases negativas, saldo reexpresado según la
fecha, motivos de ROIC y margen, años mezclados, múltiplos con denominadores
≤ 0 y EV con deuda o caja ausentes), además de los ya existentes para filings
posteriores a la fecha (`test_screener_asof`, `test_edgar`) y restatements
posteriores (`test_edgar_historical_pit`).
