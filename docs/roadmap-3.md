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
