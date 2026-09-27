# Preregistro: la idea de GABI con 60 años y varios mercados (#45)

Escrito antes de calcular la mezcla (2026-09-27). La especificación exacta está
en [`preregistro.json`](preregistro.json), con su SHA-256
(`factor_history.spec_hash()`), y en la tabla `experiments` (familia `stat_5`).

## Pregunta

¿Tiene la **idea** de GABI (valor 30 %, calidad/rentabilidad 35 %, momentum
25 % y bajo riesgo 10 %) una prima fiable cuando se mira con mucha más historia
y en mercados que no se usaron para diseñarla?

## Datos (gratuitos, Kenneth French Data Library, mensuales)

| Ingrediente | EE. UU. (desde 1963-07) | Europa, Japón, Asia-Pacífico sin Japón (desde 1990-11) |
| --- | --- | --- |
| Valor | HML | HML |
| Calidad/rentabilidad | RMW | RMW |
| Momentum | Mom | WML |
| Bajo riesgo | quintil de menor varianza − quintil de mayor varianza | no disponible (pesos reescalados sobre 0,9) |

Son carteras «largo-corto»: compran lo que el factor favorece y venden lo que
desfavorece. Miden si el criterio ordena el mercado, que es la prueba que GABI
no superó en el #40.

## Pruebas

- **Principal**: EE. UU. 1963-07 → 2015-12, antes del diseño de GABI. Media
  mensual de la mezcla > 0, t Newey-West, unilateral, α = 5 %.
- **Réplicas** (corrección de Holm sobre las 3): Europa, Japón y Asia-Pacífico
  sin Japón, 1990-11 → último mes publicado.
- **Descriptivas**, que no deciden nada:
  - EE. UU. 2016–2025, la muestra de diseño;
  - cada factor por separado;
  - décadas;
  - peor racha;
  - correlaciones entre factores.

## Decisión

| Resultado | Condición |
| --- | --- |
| Idea respaldada | principal significativa y al menos 2 de 3 réplicas significativas tras Holm |
| Respaldo parcial | solo una de las dos condiciones |
| Sin respaldo | ninguna |

## Lo que no demuestra

- Que la implementación concreta de GABI (sus métricas y su Top-20 del S&P 500)
  capture esa prima. Eso lo dirán el #44 y las pruebas ciegas.
- Tampoco es una prueba ciega sobre la existencia de estas primas, que están
  publicadas. Lo nuevo es la mezcla con los pesos de GABI y la regla de
  decisión fijada de antemano.
