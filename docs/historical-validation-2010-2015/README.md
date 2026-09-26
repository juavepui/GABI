# Validación histórica de GABI 2010–2015 sin reoptimizar: issue #33

Ejecución del 26 de septiembre de 2026. Es una simulación retrospectiva sobre
datos acreditados en #26–#32, no rentabilidad de una cuenta real. **No se han
tocado pesos, umbrales, fechas ni variantes** después de ver estos resultados.

## ¿Existía ya una validación anterior a 2016?

No. Se revisaron README, `docs/`, Research Lab, Factor Lab, `stats_rigor`,
`overfitting_audit`, `variant_validation` y las auditorías existentes.
[`historical-validation-1996-2015`](../historical-validation-1996-2015/README.md)
valida datos SEC y dice expresamente que no ejecuta un backtest de
rentabilidad. La única evaluación de rentabilidad con universo completo era
[`full-universe-audit`](../full-universe-audit/README.md) (2016–2025), y esta
validación **reutiliza exactamente su arnés** (`full_universe_audit.prepare/
evaluate`, ahora con el periodo como parámetro) en lugar de crear otro.

## Configuración exacta

Idéntica a la auditoría 2016+:

- Rebalanceo trimestral los días 2 de enero/abril/julio/octubre: 24 rankings
  del 2010-01-02 al 2015-10-02; valoración final el 2016-01-04.
- Universo: todos los constituyentes de la composición de referencia de cada
  fecha (`max_symbols=None`), solo con identidad y precios acreditados (#32).
- Pesos Value/Quality/Momentum/Risk 30/35/25/10; cobertura mínima por empresa
  70 %; mínima del universo 50 %; Top-10 y Top-20 equiponderados; sin filtro de
  mercado ni banda de permanencia.
- Resultado principal: **motor V2**, 100.000 USD, 1 USD por operación y 10 pb
  de spread total, con caja y valoración diaria; SPY comprado una vez.
  Control: V1 con 10 pb por lado.
- Cortes **concluyentes**: ejecutados, con cobertura de precio acreditado ≥ 85 %
  en la auditoría trimestral previa (restricción del #28) y ≥ 50 % de
  elegibles.

## Reproducibilidad

`python -m gabi.historical_validation` (sin red). Snapshot congelado de la base
`e741df073bc4451ed31299b736a050996aa2c2ad5402341afb97fc79114a6370`; el manifiesto
de `data/historical_validation_2010_2015/` guarda el SHA-256 de cada ranking y
de las entradas (motores V1/V2, `screener_asof`, `scoring`, `identity`,
`universe`, capa histórica y auditoría trimestral de precios); `evaluate` se
niega a ejecutar si alguno cambia. Hashes del ejecutor
`9f5605eb…` y del análisis `b7c09b03…`; los de cada CSV están en
[`audit.json`](audit.json). `--analysis-only` rehace solo los análisis sobre
rankings y backtests congelados. Código: commit que añade este informe.

## 1. Calidad de datos por rebalanceo

Detalle completo en [`coverage-by-rebalance.csv`](coverage-by-rebalance.csv)
(constituyentes, identidad, precio acreditado, fundamentales, métricas,
elegibles y motivo de cada exclusión).

| Tramo | Constituyentes | Identidad acreditada | Precio acreditado | 13 métricas | Elegibles (≥ 70 %) | Estado |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 2010-01-02 | 499 | 479 | 0 | 0 | 0 | **descartado**: la auditoría de precios empieza con ventanas del 2010-03-31 |
| 2010-04 → 2011-01 | ~498 | 484–486 | 389–425 | 0–6 | 75–102 (15–21 %) | **descartados**: faltan fundamentales de tres años (el XBRL empieza en 2009) |
| 2011-04-02 | 497 | 485 | 429 | 51 | 243 (48,9 %) | **descartado** por poco (< 50 %) |
| 2011-07 → 2011-10 | 497 | 486 | 434–435 | 60–62 | 261–273 (53–55 %) | ejecutados, concluyentes |
| 2012-01 → 2012-07 | ~497 | 487–489 | 403–420 | 63–89 | 272–314 (55–63 %) | ejecutados, **no concluyentes** (precio acreditado 81,7–84,5 %) |
| 2012-10 → 2015-10 | 497–503 | 490–494 | 430–451 | 92–124 | 344–374 (69–75 %) | ejecutados, concluyentes |

Resumen: **24 rebalanceos previstos, 18 ejecutados, 15 concluyentes**. Cobertura
media de precio acreditado 86,7 %; elegibles medios 56,5 %, comparables a los
54–79 % de 2016–2025. Las exclusiones se reparten entre identidad no
acreditada (6–20 por fecha), sin serie de precio acreditada (41–95 desde
2010-04) y cobertura de métricas inferior al 70 % (69–332, sobre todo en 2010).

## 2. Resultado de la estrategia

| V2, 100.000 USD | Periodo | CAGR neto | Volatilidad | Sharpe | Sortino | Máx. drawdown | ES 95 % diario |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Top-10 | 2010-01-04 → 2016-01-04 | 13,32 % | 16,2 % | 0,58 | 0,82 | −22,2 % | 2,48 % |
| Top-20 | 2010-01-04 → 2016-01-04 | 13,29 % | 15,3 % | 0,61 | 0,85 | −22,1 % | 2,43 % |
| SPY | 2010-01-04 → 2016-01-04 | 12,27 % | 15,8 % | 0,52 | 0,73 | −18,6 % | 2,40 % |

El periodo completo incluye 18 meses en caja por los 6 rebalanceos descartados
(GABI no invierte hasta julio de 2011; el SPY sí). Sobre el tramo realmente
invertido:

| V2, 2011-07-05 → 2016-01-04 | CAGR | Sharpe (error estándar) | Máx. drawdown |
| --- | ---: | ---: | ---: |
| Top-10 | 18,15 % | 0,76 (±0,53) | −22,2 % |
| Top-20 | 18,11 % | 0,80 (±0,54) | −22,1 % |
| SPY | 11,75 % | 0,50 (±0,50) | −18,4 % |

Rotación media 84 % (Top-10) y 68 % (Top-20) por rebalanceo; costes totales
1.337 y 1.309 USD. El control V1 (18 trimestres, 10 pb por lado) da 18,0 % y
18,2 % anual frente a 11,7 % de SPY. El Top-20 supera al SPY en 11 de 18
trimestres, con un exceso medio de 1,55 puntos por trimestre.

**Resultado estricto**: Top-10 sí. En Top-20, 4 posiciones se valoraron al
último precio sin evento confirmado (`strict_result=False`): NVLS (canje por
acciones de Lam Research en 2012), GOOG y GOOGL (sucesión a Alphabet en
2015-10, cuyo CIK aún no tenía identidad acreditada) y ANDV (FINSABER termina
el 31-12-2015, un día antes de la valoración final).

## 3. Benchmarks del universo cubierto y sesgo de exclusión

Por trimestre en [`benchmarks-by-period.csv`](benchmarks-by-period.csv); tasas
anualizadas sobre los 18 trimestres ejecutados:

| Referencia | Anualizado |
| --- | ---: |
| GABI Top-20 (V1, sin costes de caja) | 18,2 % |
| SPY | 11,7 % |
| Universo elegible, equiponderado | 11,5 % |
| Universo elegible, ponderado por capitalización | 9,6 % |
| Cota baja del universo completo equiponderado (excluidos como el peor decil) | 4,4 % |
| Cota alta del universo completo equiponderado (excluidos como el mejor decil) | 18,9 % |

En los 15 trimestres concluyentes el resultado va en la misma dirección:
Top-20 +91,1 % acumulado frente a +43,3 % del SPY y +45,2 % del universo
elegible equiponderado.

**Retorno implícito de los excluidos: no identificable.** La restricción del
#28 pedía estimarlo como SPY menos la contribución de los cubiertos ponderada
por *public float* SEC. Tras descartar pesos imposibles (un float XBRL de
1,2·10¹⁶ USD en VIAB, por ejemplo), los cubiertos pesan el 90–95 % y su
retorno ponderado queda 0,47 puntos por trimestre **por debajo** del SPY. Esa
diferencia se divide por el peso excluido (un factor de amplificación medio de
14×) y sale un retorno implícito del 45 % anual, que no es creíble. Los pesos
por float, tomados de portadas 10-K con meses de antigüedad, no reproducen los
pesos reales del índice con la precisión necesaria. **Con datos gratuitos no
puede separarse el retorno de los excluidos del error de ponderación**; la
cifra se conserva en el CSV solo como diagnóstico.

## Conclusión

1. **Datos**: 2010-01 a 2011-04 no son evaluables. El primer corte no tiene
   precios acreditados y los cinco siguientes no llegan al 50 % de elegibles
   por falta de fundamentales de tres años. Tres cortes de 2012 se ejecutan,
   pero no son concluyentes (precio acreditado < 85 %). La validación útil son
   **15 trimestres, de 2011-07 a 2015-10**.
2. **Estrategia**: en esos trimestres GABI V2 Top-10/20 obtuvo unos 6,4 puntos
   de CAGR más que el SPY y más que el universo que podía elegir, con más
   drawdown (−22 % frente a −18 %). Va en la misma dirección que 2016–2025
   (Top-20: 21,1 % frente a 15,0 %).
3. **Evidencia**: el exceso **no es estadísticamente significativo** (Sharpe
   0,80 ± 0,54 frente a 0,50 ± 0,50 en 4,5 años) y la cota alta de
   sensibilidad del universo completo (18,9 %) queda por encima del resultado
   de GABI. Por tanto, 2010–2015 **no contradice** la hipótesis, pero tampoco
   permite afirmar que GABI supere al S&P 500 fuera de la muestra de diseño.

## Sesgos residuales que no pueden eliminarse con fuentes gratuitas

- **Exclusión no neutral**: los miembros que salen del índice en el año
  siguiente tienen un 58,7 % de cobertura acreditada frente al 87,8 % del
  resto, y el quintil de menor tamaño un 82 % frente al 88–92 %. GABI no podía
  elegir esas empresas y no se sabe cómo habrían rendido.
- **Retorno de los excluidos**: no identificable con pesos de *public float*
  (ver sección 3).
- **Eventos terminales con acciones o mixtos** (18 fusiones, 4 canjes) y
  sucesiones sin CIK sucesor acreditado quedan valorados al último precio y
  marcados como no estrictos.
- **Composición comunitaria** (fja05680) y sectores aproximados (no hay GICS
  histórico gratuito).
- **Fundamentales de 2010**: el XBRL de SEC empieza en 2009, así que las
  métricas de crecimiento a tres años no existen hasta 2011–2012.
- **Estabilidad de 2016+**: el Ranking con universo completo de 2016-01-02,
  2019-07-02, 2022-04-02 y 2025-07-02 es idéntico (mismo hash) con el código
  anterior y el posterior a la capa histórica, así que los resultados de
  2016–2025 no cambian por esta integración.

## Rebalanceos descartados o degradados

| Fecha | Estado | Motivo |
| --- | --- | --- |
| 2010-01-02 | descartado | cobertura insuficiente del universo (0/499): sin ventana de precio acreditada previa |
| 2010-04-02 | descartado | cobertura insuficiente del universo (75/499) |
| 2010-07-02 | descartado | cobertura insuficiente del universo (78/499) |
| 2010-10-02 | descartado | cobertura insuficiente del universo (86/497) |
| 2011-01-02 | descartado | cobertura insuficiente del universo (102/497) |
| 2011-04-02 | descartado | cobertura insuficiente del universo (243/497) |
| 2012-01-02 | no concluyente | precio acreditado 84,5 % (< 85 %) |
| 2012-04-02 | no concluyente | precio acreditado 81,7 % |
| 2012-07-02 | no concluyente | precio acreditado 82,1 % |
