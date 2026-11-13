# Preregistro: hipótesis de valor con validación solo prospectiva (#43)

Escrito antes de calcular nada con esta especificación (2026-09-27). La
especificación exacta, el plan secuencial y el id de la prueba ciega están en
[`preregistro.json`](preregistro.json), con su SHA-256
(`value_hypothesis.spec_hash()`), y en la tabla `experiments` (familia
`r4_value`, etapa `LIVE_FORWARD`).

## Por qué esta hipótesis y por qué solo prospectiva

- **Origen**:
  - El #35 mostró que GABI supera al SPY sin significación.
  - El #40 mostró que su puntuación **no ordena** el S&P 500 mejor que el azar.
  - Por bloques, solo valor apuntaba algo (IC 0,026, t 1,32).
- **Decisión del propietario**: formular una hipótesis de valor.
- **Consecuencia**: como se eligió **después** de ver 2011–2025, ese periodo **no
  cuenta como evidencia**. Solo la prueba prospectiva puede validarla.
  Tampoco se puede usar el periodo anterior a 2010, que no es viable (#41).
- **Base en la literatura**: el composite de valor (E/P, B/P y EBITDA/EV) es el
  clásico (Fama-French 1992; Lakonishok-Shleifer-Vishny 1994; Loughran-Wellman
  2011; Asness-Moskowitz-Pedersen 2013).

## Especificación (congelada)

| Elemento | Valor |
| --- | --- |
| Modelo | `GABI-VALUE-v1` |
| Puntuación | bloque de valor de GABI sin cambios: PER, P/VC y EV/EBITDA, percentiles dentro del sector, pesos valor 100 % |
| Universo | S&P 500 vigente en cada fecha, con el mismo filtro de datos que GABI (composite no vacío y cobertura ≥ 70 % de las 13 métricas) |
| Cartera | Top-20 equiponderado, rebalanceo trimestral |
| Primer registro | **2026-12-21**, el mismo día que la prueba ciega de GABI, con datos refrescados |
| Registro | `blind_validation`, prueba nueva con cadena de hashes, y además la puntuación completa del universo en cada rebalanceo, también con hash |

## Pruebas y revisiones

- **Principal**: IC de Spearman trimestral entre la puntuación registrada y el
  retorno del trimestre siguiente (media, t unilateral). Según el #39, es la
  prueba con más potencia.
- **Secundarias**, con corrección de Holm: exceso trimestral del Top-20 frente
  al SPY y frente a RSP (S&P 500 equiponderado).
- **Revisiones secuenciales** con umbrales O'Brien-Fleming (gasto de alfa de
  Lan-DeMets, α unilateral del 5 %). Solo se miran resultados en estas fechas:

| Revisión | Trimestres | Umbral z |
| --- | ---: | ---: |
| 2029-12-21 | 12 | 3,39 |
| 2032-12-21 | 24 | 2,28 |
| 2036-12-21 | 40 | 1,68 |

- **Decisión**:
  - si la prueba principal cruza el umbral en una revisión, hay evidencia de
    capacidad predictiva del valor;
  - si no, se continúa sin cambios hasta la siguiente revisión;
  - si no lo cruza en la última revisión, no hay evidencia.

## Reglas

- El modelo no cambia hasta la última revisión. Si cambia, el registro
  prospectivo termina en esa fecha.
- Cada rebalanceo se registra a tiempo (el próximo, el 2026-12-21, junto con la
  prueba de GABI). Las cadenas de hashes deben estar íntegras en cada revisión.
- Es la configuración número 30 del recuento de múltiples pruebas.
- La prueba ciega de GABI (id 1) no se toca.

## Cambio técnico asociado

`blind_validation.record_rebalance` usaba siempre los pesos por defecto al
seleccionar, fueran cuales fueran los registrados en la validación. Para la
prueba de GABI (id 1) era lo mismo, porque sus pesos son esos. Ahora usa los
pesos de cada validación. También guarda, si la validación lo activa, la
puntuación completa del universo en una tabla aparte, sin tocar los periodos
ni sus hashes.
