# Controles de datos imposibles (#295) y GABI-MF-v3

La política `input-checks-v1` (`backend/src/gabi/domain/market/input_checks.py`)
separa dos cosas: lo que se bloquea y lo que solo se marca.

## Qué bloquea

`price_sync.clean_prices` ya rechazaba antes de esta issue, y sigue igual:

- precios no positivos o no finitos;
- máximos o mínimos incoherentes;
- sesiones duplicadas.

La descarga no se guarda.

## Qué marca

El dato se guarda y se muestra con su motivo:

| Regla | Umbral | Efecto en un modelo con controles |
| --- | --- | --- |
| Campo de Yahoo fuera de rango (`RANGES`, extremos incluidos) | p. ej. PER (0, 1000], margen ≤ 100 %, deuda/patrimonio ≤ 10.000 % | ese campo puntúa como ausente |
| Movimiento diario de más del 50 % sin split en ±3 días, últimas 252 sesiones | `JUMP = 0.5` | las métricas de precio puntúan como ausentes |
| Capitalización de Yahoo frente a cierre × acciones SEC | ±50 % | solo informa |

El cruce de capitalización no deja de puntuar nada. Las empresas con varias clases de
acciones declaran a la SEC las acciones de una sola clase y darían falsos avisos.

## Versión del modelo (ADR 0008)

- Que un dato marcado deje de puntuar cambia el ranking, así que la política se aplica solo
  en una versión declarada con `input_checks`: `GABI-MF-v3`, que es `GABI-MF-v2` más
  `input-checks-v1`.
- El propietario la activó el 2026-11-04. Empieza sin evidencia y no hereda la de la v2.
- `GABI-MF-v1` (sellado) y `GABI-MF-v2` siguen puntuando cada valor tal como viene. La
  hipótesis sellada no admite controles.
- El registro diario anota la decisión de v1 y la del modelo activo en la misma
  cadena. Las huellas de código del modelo activo incluyen `input_checks.py`.
- Desde el 2026-11-06 el modelo activo es `GABI-MF-v4` (#339), que mantiene estos
  controles y solo cambia el crecimiento de ingresos (ver `revenue-growth.md`).
- Desde el 2026-11-06 (#347) el modelo activo es `GABI-MF-v5`, el modelo tal como
  se probó con datos del pasado. **No usa estos controles al puntuar**, porque el
  modelo probado no los tenía; el informe sigue disponible como aviso (ver
  `modelo-v5.md`).

## Dónde se ve

«Calidad de los datos» → «Datos imposibles o sospechosos». Es un trabajo explícito
(`input_checks`) que recorre la caché del universo, lista cada dato marcado y su motivo,
y dice si el modelo activo los aplica. No descarga nada.
