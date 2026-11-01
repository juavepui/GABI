# Puerta de datos de NSI-v1: emisión neta de acciones (#252)

**Estado: PASA (2026-11-01).** La definición se fijó en el commit 0e46fb0, antes
de descargar o ejecutar nada. No se ha leído ningún rendimiento. El siguiente paso
es el preregistro definitivo, que debe aprobar el propietario antes de cualquier
cálculo de retornos.

Es la candidata de reserva de [#268](268-mapa-hipotesis.md), apartado 5. Pasa a
ser la siguiente tras el cierre de [CBOP-v1](cbop-v1-puerta-datos.md) por
inviable. Antes de mirar un solo retorno, debe pasar la puerta de acreditación
de splits y clases de acciones que exigía #268.

## Medida

Pontiff y Woodgate (2008) miden la emisión como el cambio logarítmico de las
acciones en circulación ajustadas por splits. Sin CRSP, el ajuste por splits
está en el propio filing:

```
emisión = ln(acciones medias básicas del ejercicio t / acciones medias básicas de t−1)
```

- **Mismo 10-K para los dos ejercicios.** Las dos cifras salen del mismo 10-K, de
  su columna del año y de la comparativa. La norma ASC 260 obliga a reexpresar
  retroactivamente la comparativa por splits y dividendos en acciones, así que
  las dos están en la misma base. Así se evita la serie por ticker y la
  reconstrucción de splits que bloquearon la auditoría de capital de #60, que
  dio 0 de 57 fechas.
- **Etiquetas:** `WeightedAverageNumberOfSharesOutstandingBasic` y, si un filing
  no la presenta, `WeightedAverageNumberOfSharesOutstandingBasicAndDiluted`. La
  etiqueta se elige filing a filing, nunca mezclando dos en el mismo filing.
- **Medias en lugar de acciones a cierre:** se usan acciones medias porque la
  portada (`dei`) da una fecha posterior al cierre y no tiene comparativa. Es
  una aproximación declarada a las acciones a cierre del artículo.
- **Filings y periodos válidos:**
  - Solo cuentan los 10-K originales presentados antes de la sesión de señal.
    Los 10-K/A quedan fuera.
  - Los periodos deben ser anuales, de 340 a 380 días.
  - El año ancla tiene como máximo 550 días.
  - Dos valores distintos para el mismo año en el mismo filing dejan el dato
    inutilizable.

## Auditoría de la reexpresión (splits y clases)

La premisa de ASC 260 se comprueba en lugar de suponerla. La comparativa del
10-K de t debe coincidir con la cifra que el 10-K de t−1 dio para su propio
ejercicio:

- **`reconciled`:** coincide dentro del 0,5 %.
- **`split_restated`:** difiere en un cociente de split sencillo, sin otra
  causa. Los cocientes admitidos son 1,25, 1,5, 2, 3, 4, 5, 6, 7, 8, 10, 15 y 20,
  y sus inversos, con una tolerancia del 0,5 %.
- **`mismatch`:** cualquier otra diferencia. Indica una reexpresión no fiable,
  clases de acciones mezcladas o un cambio de perímetro.
- **`no_previous_filing`:** no hay un 10-K anterior con XBRL contra el que
  comprobar. No cuenta en el denominador de conciliación.

## Criterio de la puerta

Fechas de señal: la primera sesión de julio de cada año de 2011 a 2025, con el
periodo observado exigido. Universo: todos los miembros del S&P 500 en la señal,
financieras incluidas, como en Pontiff y Woodgate. En **cada** fecha deben
cumplirse las dos condiciones:

1. **Cobertura ≥ 70 %** de los miembros con la emisión calculada. Los miembros
   sin identidad histórica aceptada cuentan como ausentes.
2. **Conciliación ≥ 90 %** de los emisor-fechas auditables (`reconciled` o
   `split_restated`).

Si alguna fecha falla, la decisión es `close_unfeasible`, sin enmiendas
posteriores. La lección de CBOP-v1 se aplicó antes de ejecutar: las etiquetas
alternativas y la tolerancia quedan fijadas aquí.

La identidad, la composición y la descarga son las de la puerta de CbOP. Las
acciones se guardan en su propio almacén, `data/nsi/facts.db`.

```powershell
uv run --project backend python -m gabi_cli research nsi-gate --download
uv run --project backend python -m gabi_cli research nsi-gate --audit   # escribe docs/research/nsi-v1/cobertura.json
```

## Resultado (2026-11-01)

**Descarga.** Los 767 CIK, en 1.534 peticiones, sin ninguna ausencia. El
manifiesto SHA-256 `018d3dd7…` está en [`nsi-v1/cobertura.json`](nsi-v1/cobertura.json).

**Decisión: `continue_to_exploratory`.** Las 15 fechas pasan las dos condiciones.

| Señal | Miembros | Con emisión | Cobertura | Auditables | Concilian | Reexpresadas por split |
|---|---:|---:|---:|---:|---:|---:|
| 2011-07-01 | 497 | 396 | 79.7 % | 202 | 96.5 % | 4 |
| 2012-07-02 | 497 | 462 | 93.0 % | 379 | 96.0 % | 13 |
| 2013-07-01 | 497 | 465 | 93.6 % | 451 | 97.3 % | 9 |
| 2014-07-01 | 498 | 469 | 94.2 % | 458 | 98.7 % | 15 |
| 2015-07-01 | 500 | 474 | 94.8 % | 462 | 99.6 % | 8 |
| 2016-07-01 | 479 | 454 | 94.8 % | 446 | 99.1 % | 10 |
| 2017-07-03 | 489 | 464 | 94.9 % | 453 | 99.1 % | 8 |
| 2018-07-02 | 496 | 469 | 94.6 % | 461 | 99.3 % | 7 |
| 2019-07-01 | 497 | 470 | 94.6 % | 461 | 99.8 % | 5 |
| 2020-07-01 | 501 | 480 | 95.8 % | 467 | 98.7 % | 2 |
| 2021-07-01 | 501 | 480 | 95.8 % | 475 | 100.0 % | 7 |
| 2022-07-01 | 498 | 482 | 96.8 % | 474 | 99.6 % | 9 |
| 2023-07-03 | 503 | 485 | 96.4 % | 483 | 98.6 % | 7 |
| 2024-07-01 | 503 | 483 | 96.0 % | 479 | 99.0 % | 6 |
| 2025-07-01 | 503 | 486 | 96.6 % | 480 | 99.6 % | 13 |

**Lectura.**
- **Cobertura:** está entre el 80 y el 97 %.
  - El año más débil es 2011, el de entrada en XBRL: 89 miembros no tenían
    todavía un 10-K con XBRL.
  - Ese año solo hay 202 emisor-fechas auditables, porque muchos no tenían
    10-K XBRL anterior. Aun así, concilia el 96,5 %.
- **Conciliación:** está entre el 96 y el 100 %.
  - La reexpresión por splits que exige ASC 260 se cumple en la práctica: entre
    2 y 15 emisores por año aparecen reexpresados por un split.
  - Hay casos `mismatch`, por ejemplo en 2020 AIV, GRMN, HST, PCAR, VIAC y WRB.
    Las causas posibles son REIT con unidades operativas, fusiones de clases o
    dividendos en acciones con proporciones no sencillas, pero no se han
    verificado una a una.
- **Riesgo de sesgo que queda:** entre 4 y 14 miembros por año tienen el último
  10-K demasiado antiguo o una identidad sin resolver.

## Siguiente paso

Antes de calcular ningún retorno, el propietario debe aprobar un preregistro
definitivo con estos elementos:
- señal, cartera, rebalanceo y banda;
- benchmark S&P 500 TR en EUR con los mismos flujos;
- costes BASE y STRESS de V3;
- ventanas, test estadístico y presupuesto de intentos;
- criterio de abandono.

Después se congela con el hash del commit y se registra en el ledger de #60.
