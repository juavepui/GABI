# Crecimiento de ingresos revenue-growth-v1 (#339) y GABI-MF-v4

## Qué problema resuelve

Cada empresa declara sus ingresos a la SEC con una etiqueta XBRL. La regla V1
(`sec_facts`) toma la primera etiqueta candidata con datos y solo une otra si
coinciden en algún año. Cuando una empresa cambia de etiqueta sin año en común,
la serie V1 se para y su crecimiento a 3 años describe años pasados (GE: hasta
2018; Morgan Stanley: hasta 2014).

## La regla

- (a) La serie empieza por la etiqueta con el año más reciente; las demás solo se
  unen si cuadran, como en V1.
- (b) Si la serie va por detrás del último beneficio anual más de 45 días, el
  crecimiento queda **sin dato** (`stale`), nunca uno viejo.
- El cálculo del crecimiento es el de V1 (cuatro cierres anuales seguidos, ambos
  extremos positivos).

Se guarda en `sec_revenue_growth`, calculada desde los hechos guardados en la
sincronización SEC y en el refresco diario; no descarga nada.

## Versión del modelo (ADR 0008)

- `sec-metrics-v2.2` = ROIC de V2.1 + este crecimiento.
- `GABI-MF-v4` = `GABI-MF-v3` con `sec-metrics-v2.2`. El propietario la activó el
  2026-11-06. Empieza sin evidencia y no hereda la de la v3.
- Desde el 2026-11-06 el modelo activo es `GABI-MF-v5` (#347), que puntúa el
  crecimiento de ingresos como el motor de la prueba histórica, no con esta regla
  (ver `modelo-v5.md`). v4 sigue declarada.
- `sec_facts`, V1 y las versiones anteriores no cambian; la hipótesis sellada y los
  estudios prospectivos siguen con V1.

## Efecto medido al activarla (2026-11-06, ranking del día)

Cambió el crecimiento de 23 de 503 empresas (15 a un valor actual, 8 a «sin dato»).
Las 20 primeras fueron las mismas. Detalle en el comentario de #339.

## Límites conocidos

- Bancos (MS, WFC, FITB, RF): ninguna etiqueta guardada da sus ingresos totales; con
  esta regla quedan sin dato en vez de con un crecimiento viejo o de solo comisiones.
- Caja libre: `CAPEX_TAGS` no reconoce algunas etiquetas de inversión (p. ej.
  `PaymentsToAcquireProductiveAssets`); queda para otra versión.
