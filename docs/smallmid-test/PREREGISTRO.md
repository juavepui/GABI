# Preregistro: GABI fuera del S&P 500, con cotas para los datos que faltan (#44)

Escrito antes de reunir precios o calcular rankings (2026-09-27). La
especificación exacta está en [`preregistro.json`](preregistro.json), con su
SHA-256 (`smallmid_test.spec_hash()`), y en la tabla `experiments` (familia
`stat_4`). Decisión del propietario: intentarlo, aceptando que tardará meses
por el límite de Tiingo.

## Por qué

GABI se diseñó con el S&P 500. Las empresas medianas y pequeñas de EE. UU. no se
usaron para diseñarlo, así que son una prueba fuera de muestra en el mismo
periodo. Hay unas 1.800–2.400 por fecha, lo que multiplica la potencia de la
prueba de sección cruzada (#39).

## Universo (solo datos SEC)

- **Criterio**: *public float* SEC fechado en los 15 meses anteriores, entre
  300 millones y 20.000 millones de USD.
- **Exclusión**: los emisores del S&P 500 de esa fecha.
- **Fechas**: 57 rebalanceos trimestrales, de 2011-07-02 a 2025-07-02.
- **Supervivencia**: incluye a las empresas que después desaparecen.

## Modelo: GABI sin cambios

- Composite 30/35/25/10 con las mismas 13 métricas.
- Elegibles: composite no vacío y cobertura ≥ 70 %.
- Fundamentales: SEC por CIK, point-in-time, con la corrección del #38.
- **Sector**: derivado del código SIC de la SEC. GABI usa fotos de Yahoo que no
  existen para estas empresas; el sector solo decide con qué empresas se
  compara cada una.

## Precios e identidad

- **Fuentes**: Yahoo (tickers vigentes, archivado aparte sin tocar la caché
  operativa), Tiingo (deslistados) y Nasdaq Data Link WIKI (hasta 2018).
- **Ticker**: el vigente de la SEC, o el declarado por el propio emisor en un
  10-K o en una portada XBRL.
- **Serie**: aceptada solo si pasa la comprobación de nivel de precio de la
  SEC (#28).

## Prueba

- **Principal**: IC de Spearman trimestral entre la puntuación y el retorno del
  trimestre siguiente; media con t Newey-West unilateral, α = 5 %.
- **Cotas para las elegibles sin retorno siguiente**:
  - *Adversa*: las que puntúan por encima de la mediana reciben el percentil
    10 del retorno del trimestre, y las de debajo, el percentil 90. Es el peor
    caso para GABI.
  - *Favorable*: el caso simétrico.
  - *Casos completos*: solo las empresas con retorno.

## Decisión

| Resultado | Condición |
| --- | --- |
| Robusta | IC > 0 con p < 0,05 también con la cota adversa |
| Condicionada a los datos | p < 0,05 con casos completos, pero no con la cota adversa |
| No concluyente | IC > 0 con p ≥ 0,05 en casos completos |
| Sin capacidad predictiva | IC ≤ 0 en casos completos |

## Se informará siempre

- La cobertura por trimestre.
- Las empresas excluidas por falta de precio, separando las que desaparecen de
  las que no. Es el sesgo que no puede eliminarse con datos gratuitos.
- Quintiles, Top-20 frente al universo e IC por ventana.
