# Roadmap #3: calidad persistente a precio razonable

El issue [#18](https://github.com/juavepui/GABI/issues/18) reúne varias
hipótesis que deben validarse por separado. Mantenerlas como una sola prueba
permitiría elegir retrospectivamente la mejora que más suba el CAGR.

## Entregables separados

1. **Calidad persistente**: métricas anuales point-in-time de estabilidad de
   ROIC y margen operativo, años con FCF positivo, conversión de FCF sobre
   ventas y crecimiento de ventas por acción. Esta primera entrega solo añade
   observabilidad al ranking histórico; no cambia los pesos congelados.
2. **Precio frente a expectativas**: escenario de crecimiento/valoración o
   reverse DCF, con supuestos fijados antes de la evaluación y sin mezclarlo
   con los múltiplos actuales.
3. **Rotación selectiva**: regla explícita para sustituir una posición solo
   cuando la mejora esperada supere costes y deterioro de la tesis.
4. **Asignación de capital**: dilución, recompras y reinversión/adquisiciones,
   con datos disponibles en la fecha de decisión.
5. **Validación de cartera**: cada variante se ejecuta sobre el universo
   histórico completo en V2, con el Composite actual como control fijo, y se
   compara en CAGR neto, ES, drawdown, turnover y exposición a factores.

### E3 — Rotación selectiva y costes (#21)

Implementado en los motores V1 y V2. `rotation_policy.select_with_score_hurdle`
separa tres pasos: el ranking aporta la señal, la política decide si la
mejora del Composite supera un umbral fijado ex ante y el motor ejecuta la
operación aplicando los costes calibrados de eToro. Con umbral cero se conserva
el control top-N estricto; el umbral positivo reduce sustituciones pequeñas sin
ajustarse a la rentabilidad observada. La pantalla Ranking histórico expone el
parámetro para ambos motores. La comparación empírica completa de variantes
(CAGR neto, turnover, coste, ES y drawdown) queda reservada al experimento de
validación del issue #23.

### E4 — Asignación de capital (#22)

Implementado como información descriptiva point-in-time en el ranking
histórico. `capital_allocation.metrics` usa únicamente hechos XBRL publicados
antes de cada fecha y expone dilución/reducción de acciones, recompras,
emisión neta, reinversión (CAPEX frente a flujo operativo) y pagos por
adquisiciones. Cada fila incluye cobertura (`capital_allocation_coverage`): un
dato ausente queda en `None` y nunca se rellena con el valor actual ni con
cero. Estas columnas no entran en el `composite_score`; sirven para comprobar
si aportan información incremental frente a ROIC, márgenes, crecimiento y
valoración antes de diseñar una variante experimental.

Las entregas 2–5 permanecen pendientes hasta que la primera tenga cobertura y
pruebas suficientes. Ninguna entrega puede modificar la prueba ciega existente
ni convertirse en la nueva configuración elegida por mirar el resultado.

## Entrega 1: observabilidad implementada

`src/gabi/quality_persistence.py` calcula estas métricas desde hechos anuales
de EDGAR ya recortados por `filed_date`. `screener_asof` las incorpora a cada
ranking histórico sin alterar `composite_score`, `quality_score`, pesos ni
criterios de elegibilidad. Así se puede medir la hipótesis antes de decidir si
merece convertirse en una variante de selección.

La función no inventa estabilidad: una empresa con un solo año disponible
conserva el recuento, pero no obtiene una serie larga por interpolación. Las
pruebas cubren años positivos, conversión de FCF, crecimiento por acción y
ausencia de datos.

## Entrega 2: precio frente a expectativas

`src/gabi/valuation_expectations.py` añade un reverse DCF descriptivo. Resuelve
el crecimiento constante de FCF a cinco años que hace coincidir el valor
presente con el valor de empresa observado, usando una tasa de descuento fija
del 9% y crecimiento terminal del 2,5%. `screener_asof` muestra el crecimiento
implícito, el FCF CAGR histórico y la brecha entre ambos.

Los supuestos están fijados en el código, las entradas se recortan por fecha de
presentación SEC y la métrica no modifica el Composite. No se presenta como
precio objetivo: FCF negativo, valor empresarial no positivo o ausencia de
histórico devuelven una métrica vacía. La validación de rentabilidad de una
variante de selección queda para el issue #23.
