# Preregistro R3 E6: calidad persistente a precio razonable y ventana común de riesgo (#36, #37)

Escrito **antes de ejecutar ningún backtest** (2026-09-27). La especificación
exacta está en [`preregistro.json`](preregistro.json), con su SHA-256
(`r3_experiment.spec_hash()`), y en la tabla `experiments` (familia `r3_e6`).
Si la especificación cambiara, el código se niega a ejecutar. No se lee ni se
modifica la prueba ciega prospectiva.

## Hipótesis

Puntuar la persistencia de la calidad y el precio frente a expectativas (E6a),
o medir el riesgo en una ventana común de tres años (E6b), mejora la cartera
V2 Top-20 frente al Composite vigente sin empeorar su riesgo de cola.

## Control y variantes (solo dos)

| Configuración | Qué cambia respecto al control |
| --- | --- |
| `control_composite` | Nada: Composite vigente, pesos 30/35/25/10 y métricas de `scoring.SCORE_METRICS`. |
| `e6a_calidad_persistente` | Calidad = ROIC, margen operativo, CAGR de ventas y de FCF **+ `quality_persistence_score`** (fracción de años con ROIC, margen y FCF positivos; más es mejor) **+ `roic_persistence_std`** (dispersión del ROIC; menos es mejor). Ambas solo con al menos 3 ejercicios de ROIC. Valor = PER, P/VC, EV/EBITDA **+ `expectations_gap`** (CAGR histórico del FCF menos el crecimiento implícito del reverse DCF con descuento del 9 %, crecimiento terminal del 2,5 % y 5 años; más es mejor). |
| `e6b_riesgo_756` (#37) | `volatility` y `max_drawdown` sobre las **últimas 756 sesiones** (757 cierres) de la misma serie acreditada y con la misma función `risk.compute_risk_metrics`, en vez de toda la serie. |

- **Pesos y métricas**: los pesos por bloque no cambian. Cada bloque promedia
  sus percentiles sectoriales con igual peso, con el código de
  `scoring.build_scores` sin modificar.
- **Elegibles**: el conjunto elegible es **el del control** en las tres
  configuraciones (composite no vacío y cobertura ≥ 70 % de las 13 métricas
  del control). Por tanto, fechas, universo y rebalanceos ejecutados son los
  mismos. Las variantes solo reordenan dentro de ese conjunto.
- **Comprobación previa, sin resultados**: el control recalculado reproduce el
  composite congelado de las 63 fechas (diferencia máxima 1,4e-14).
- **Cobertura, dato descriptivo**: el 18-07-2018 `expectations_gap` existe
  para el 41 % de los miembros, `quality_persistence_score` para el 96 % y
  `roic_persistence_std` para el 81 %; el 72 % tiene al menos 3 ejercicios.
  Donde falta una métrica, el bloque promedia las disponibles, igual que el
  control.

## Muestra, motor y costes

- **Rankings**: los congelados de la variante principal del #35
  (`acreditado-38`: capa acreditada + corrección #38), con su snapshot,
  hashes y fingerprint.
- **Rebalanceos**: 2010-01-02 → 2025-10-02, trimestral el día 2. Se invierte
  desde 2011-07-02 (los trimestres anteriores no tienen cobertura, como en el
  #33 y el #35).
- **Motor**: V2 en modo validación, 100.000 USD, 1 USD de comisión y 10 pb de
  spread. **Principal: Top-20**; Top-10 es secundario.
- **Ventanas**: completa 2011-07 → 2025-10, 2011–2015, 2016–2020 y 2021–2025.

## Métricas

- CAGR neto.
- ES 95/99 % diario.
- Drawdown máximo.
- Rotación, costes y beta frente al SPY, por ventana.
- FF5 + Momentum con errores HAC (#11) sobre los retornos trimestrales de
  2011-07 → 2025-07.
- Diferencia trimestral de cada variante frente al control: media, t HAC y p
  unilateral.
- PBO (CSCV, 8 bloques) sobre los 56 trimestres 2011-10 → 2025-07 de las tres
  configuraciones.
- DSR con **29 configuraciones documentadas**: las 24 del #12, los 2 umbrales
  de rotación del #23 y las 3 de este experimento.

## Regla de decisión (V2 Top-20, serie completa)

Una variante se **adopta** solo si cumple las cuatro condiciones:

- **(a)** CAGR neto ≥ el del control + 1,0 pp.
- **(b)** CAGR mejor que el control en al menos 2 de las 3 ventanas
  (2011–2015, 2016–2020, 2021–2025).
- **(c)** ES 95 % no peor en más de un 10 % relativo y drawdown máximo no peor
  en más de 3 pp.
- **(d)** p unilateral HAC de la diferencia trimestral < 0,05 tras la
  corrección de Holm sobre las 2 variantes, y DSR > 0,95.

Si cumple (a), (b) y (c) pero no (d), queda **pendiente de validación
prospectiva**. En cualquier otro caso, se **descarta**. El modelo por defecto
no cambia salvo «adoptar».

## Límites conocidos de antemano

- 2016–2025 es la muestra de diseño de GABI. Este experimento es
  retrospectivo (RESEARCH), no fuera de muestra.
- Las variantes no pueden añadir empresas que el control no considere
  elegibles. Eso aísla el efecto de la puntuación, pero no mide cambios de
  cobertura.
- La variante E6a se definió a partir de las métricas del roadmap #18 sin mirar
  su rendimiento. No hay búsqueda de pesos ni de umbrales.
