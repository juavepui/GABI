# Ampliación A3 del preregistro #44: cuándo se da por cerrada la recogida de datos

Escrita el 2026-09-28, **sin ningún ranking ni resultado del #44**. Especificación en
[`preregistro-a3.json`](preregistro-a3.json):

| Campo | Valor |
| --- | --- |
| SHA-256 de la ampliación | `c6d92d38da0dafbeb5b83342771a69bc369675d197d1f2ac7cc910e850bc3e29` |
| Amplía | preregistro `99d36edf…`, A1 `2608251c…` y A2 `39c274a0…` |
| Código | `smallmid_test.py`, SHA-256 `96d388bb…`; funciones del análisis sin cambios (`69efba58…`) |
| Experimento | id 49, familia `stat_4` |

## Por qué

Con Kaggle, la cobertura de las empresas desaparecidas subió del 34 % al 62 %, pero el tramo 2021–2025 depende
de Tiingo y su cupo mensual. Si no hay una fecha fijada de antemano, "esperar a tener un poco más de datos"
puede acabar decidiéndose, sin querer, según cómo pinten los resultados.

## Regla

- **Los datos se congelan** cuando una ejecución de Tiingo recorre la cola entera sin detenerse por el cupo, o
  el **15 de enero de 2027**, lo que ocurra antes. La tarea `periodic_tasks --tiingo` deja la marca
  `tiingo_completa.json` al completar la cola.
- **Después, una sola vez**: rankings de las 57 fechas, retornos siguientes y análisis, con la cobertura que
  haya y las cotas preregistradas (adversa, favorable y casos completos).
- **No se añaden más fuentes** ni se repite el análisis con más datos.
- `--rankings` y `--analyze` se niegan a ejecutarse mientras los datos no estén congelados.

## Por qué no se repiten #35, #36 ni #40

Kaggle solo rescataría unos 300–450 de los 20.218 casos del S&P 500 de 2016–2025: la cobertura pasaría de
alrededor del 92,5 % a alrededor del 94,5 %. La mayoría de las exclusiones se deben a que la SEC no publica el
dato para la comprobación, a identidades múltiples o a cotizaciones que empiezan tarde, no a la falta de
precio. Además, son datos ya vistos: repetir el análisis no aportaría evidencia nueva.
