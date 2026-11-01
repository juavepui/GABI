# Puerta de datos de NSI-v1: emisión neta de acciones (#252)

**Estado:** definición fijada antes de descargar o ejecutar nada. No calcula ni
lee rendimientos.

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

## Resultado

Pendiente.
