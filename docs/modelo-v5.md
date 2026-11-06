# GABI-MF-v5: el modelo probado, calculado hoy (#347)

## En pocas palabras

`GABI-MF-v5` puntúa las empresas **exactamente como el modelo que se probó con
datos del pasado**. Hasta `GABI-MF-v4`, la app usaba otra fuente para parte de
las métricas, así que lo que se veía en pantalla no era lo que se había probado.

- **Lo que se probó** (revalidación #35, variante `operativo-38`): 20,1 % al año
  frente al 15,0 % del S&P 500 entre 2016 y 2025, con un exceso trimestral
  t = 1,98. En la vista principal (`acreditado-38`), 19,4 % frente al 15,0 %,
  t = 1,40.
- **Lo que esto no dice:** que vaya a superar al índice en el futuro. Es una
  prueba con datos del pasado, sin significación estadística clara y todavía
  sin confirmar con datos nuevos (#60 sigue abierta). Puede haber sido suerte.

## Por qué

La comparación del #291 (2026-11-06) mostró que solo 7 de las 20 primeras
empresas de la app coincidían con las del cálculo histórico:

| Métrica | Hasta v4 (app) | Prueba histórica y v5 |
| --- | --- | --- |
| PER, EV/EBITDA, margen operativo | Yahoo, últimos 12 meses | SEC, último 10-K |
| Precio / valor contable, deuda / patrimonio | Yahoo, último trimestre | SEC, último 10-K |
| ROIC | `sec-metrics-v2.1` (#245) | SEC, motor histórico |
| Crecimiento de ingresos (3 años) | `revenue-growth-v1` (#339) | SEC, motor histórico |
| Crecimiento de la caja libre (3 años) | SEC | SEC, motor histórico |
| Momentum y riesgo | precios guardados | los mismos precios (ya coincidían) |

Las correcciones de v2–v4 pueden ser mejores en teoría, pero **nunca se
probaron**. Lo único con evidencia es el cálculo histórico, así que v5 usa ese.

## Qué hace

- La tarea diaria, después de actualizar los datos y antes de registrar las
  decisiones del día, ejecuta el motor histórico (`screener_asof` en modo
  operativo, #237, con la alineación de ejercicios del #38) para hoy. Después
  guarda las 8 métricas de empresa del Composite en la tabla
  `engine_fundamentals` (regla `engine-fundamentals-v1`). Tarda unos 5 minutos.
- El ranking de v5 (`sec-engine-v1`) usa esas 8 métricas en lugar de las de
  Yahoo. Si una empresa no tiene fila, o la fila tiene más de 7 días, esa
  métrica cuenta como **sin dato**: nunca se vuelve a Yahoo.
- Mismos pesos (30/35/25/10), parámetros técnicos, benchmark (SPY) y tipo sin
  riesgo (4 %). Sin controles de entrada al puntuar, porque el modelo probado
  no los tenía. El informe «Buscar datos imposibles» sigue disponible como aviso.
- La ficha y el checklist dicen de dónde sale cada valor: con v5, «SEC (10-K)».
- `ranking-parity-v2`: la comparación del #291 ejecuta el motor con la
  alineación del #38; con v5 las dos columnas deben coincidir.

## Comprobación con datos reales (2026-11-06, solo lectura)

Con el ranking de v5 calculado por el código de la app:

- Top-20 de v5 = Top-20 del motor histórico: **20 de 20** (con v4, 8 de 20).
- Correlación de puestos del Composite: **1,00**; diferencia máxima: **0,0**
  puntos.

## Cómo ponerlo en marcha

Tras integrar el cambio, hay que calcular las métricas del día una vez (después
lo hace la tarea diaria):

```powershell
backend\.venv\Scripts\python.exe -m gabi_cli periodic --motor
```

Hasta entonces, v5 no tiene métricas de empresa y casi ninguna empresa llega a
la cobertura mínima.

## Decisión

Decidido el 2026-11-06 por Claude, por delegación expresa del propietario. Su
objetivo: «el mejor modelo posible para tomar buenas decisiones y superar al
S&P 500». No se ha ajustado ningún peso ni regla mirando el pasado: eso sería
sobreajuste (que el resultado salga bien por casualidad y no se repita).
Como toda versión nueva (ADR 0008), v5 empieza sin evidencia propia. El registro
diario la sigue desde su primera noche, y la prueba de verdad llegará con los
datos nuevos.
