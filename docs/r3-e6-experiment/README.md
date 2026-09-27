# Experimento R3 E6: resultados (#36, con la variante del #37)

Preregistro: [PREREGISTRO.md](PREREGISTRO.md) y [preregistro.json](preregistro.json)
(SHA-256 `d68a50ad5a0093b12829392a86798aed676e56bae397aa157cc57f3e99aae0d1`,
commit `9069150`, tabla `experiments` ids 35–37), escrito antes de cualquier
backtest. Resultados en `experiments` (ids 38–40) y en
[analysis.json](analysis.json), con una carpeta por configuración (periodos,
NAV y ventanas V2 Top-10/20).

## Decisión

| Variante | (a) CAGR ≥ control + 1 pp | (b) mejor en 2 de 3 ventanas | (c) riesgo no peor | (d) significativa | Decisión |
| --- | :---: | :---: | :---: | :---: | --- |
| `e6a_calidad_persistente` | no | no | sí | no | **descartar** |
| `e6b_riesgo_756` (#37) | no | sí | sí | no | **descartar** |

**El modelo por defecto no cambia.** La calidad persistente a precio razonable,
tal como se preregistró, **empeora** la cartera. La ventana común de riesgo la
mejora poco y sin significación, así que se mantiene la semántica actual de
`volatility` y `max_drawdown` ([market-metrics.md](../market-metrics.md)).

## Comprobaciones

- El control recalculado reproduce el composite congelado de las 63 fechas
  (diferencia máxima 1,4e-14).
- El control reproduce **exactamente** el V2 de la serie continua del #35: la
  NAV coincide en las 3.962 sesiones.
- Las tres configuraciones ejecutan los mismos 57 rebalanceos (2011-07 →
  2025-07), con el mismo universo, los mismos elegibles y los mismos costes.
- La ventana de 756 sesiones usa la misma serie acreditada del ranking.
  Calculadas sobre toda la serie, las métricas reproducen sin discrepancias
  las de las 63 tablas congeladas.

## Resultados (V2, 100.000 USD, 1 USD + 10 pb; CAGR neto / ES 95 % diario / drawdown)

**Top-20 (principal)**

| Ventana | Control | E6a calidad persistente | E6b riesgo 756 |
| --- | --- | --- | --- |
| Completa 2011-07 → 2025-10 | 18,8 % / 2,90 % / −32,8 % | 16,9 % / 2,77 % / −34,1 % | 19,2 % / 2,86 % / −32,9 % |
| 2011–2015 | 18,0 % / 2,67 % / −21,6 % | 16,7 % / 2,57 % / −20,7 % | 17,4 % / 2,66 % / −21,6 % |
| 2016–2020 | 21,5 % / 3,35 % / −32,8 % | 19,4 % / 3,22 % / −34,1 % | 21,7 % / 3,30 % / −32,9 % |
| 2021–2025 | 16,8 % / 2,62 % / −23,1 % | 14,4 % / 2,48 % / −22,9 % | 18,5 % / 2,56 % / −20,3 % |

Serie completa, Top-20:

| Configuración | Rotación media | Costes | Beta SPY |
| --- | ---: | ---: | ---: |
| Control | 70 % | 9.956 USD | 1,00 |
| E6a | 75 % | 9.547 USD | 0,97 |
| E6b | 68 % | 9.635 USD | 1,00 |

**Top-10 (secundario)**: serie completa del 20,2 % en el control, 15,4 % en
E6a y 20,6 % en E6b. En E6a, 2021–2025 cae al 7,9 %.

## Incertidumbre y múltiples pruebas

| | Control | E6a | E6b |
| --- | ---: | ---: | ---: |
| Sharpe anual (retornos trimestrales V2) | 0,88 | 0,79 | 0,92 |
| Diferencia trimestral frente al control | — | −0,44 pp (t HAC −1,86) | +0,08 pp (t HAC 0,55) |
| p unilateral / p Holm | — | 0,97 / 0,97 | 0,29 / 0,59 |
| DSR (29 configuraciones documentadas) | — | 0,97 | 0,98 |
| Alfa FF5 + Mom anual (t HAC) | +5,6 % (2,35) | +3,5 % (1,81) | +6,1 % (2,86) |

- **PBO** (CSCV, 8 bloques, 56 trimestres, 3 configuraciones): **0,34**.
- **DSR**: supera 0,95 en ambas variantes porque el Sharpe de toda la familia
  es alto. Pero lo que decide es la mejora frente al control, y esa no es
  significativa en ninguna: E6a va en la dirección contraria y E6b está
  dentro del ruido.
- **Alfa FF5 + Mom**: el del control (+5,6 %, t 2,35 en 57 trimestres) indica
  que el Composite no se explica solo por exposiciones a mercado, tamaño, value,
  rentabilidad, inversión y momentum. Es una muestra retrospectiva que incluye
  el periodo de diseño, y la exposición a RMW sube en E6a sin mejorar el
  resultado.

## Lectura

- **E6a**: añadir la persistencia al bloque de calidad y la brecha de
  expectativas al de valor desplaza la cartera hacia empresas maduras y
  estables. Rota más (75 % frente a 70 %) y rinde menos en todas las ventanas.
  La brecha de expectativas solo existe para ~41 % de los miembros (exige FCF
  y EV positivos). Donde falta, el bloque de valor pesa solo con los múltiplos,
  y eso introduce ruido de cobertura. Queda como evidencia en contra de esta
  especificación, no de toda idea de calidad persistente. Cualquier otra
  especificación sería un experimento nuevo, preregistrado y contado como
  prueba adicional.
- **E6b**: medir el riesgo en 3 años cambia poco la cartera. Mejora 2021–2025
  (+1,7 pp) y empeora 2011–2015 (−0,7 pp). Se descarta por la regla, no por
  riesgo.

## Límites

- Todo el intervalo es retrospectivo e incluye la muestra de diseño de GABI.
  La prueba ciega prospectiva no se ha leído ni modificado.
- Las variantes no pueden cambiar el conjunto de elegibles del control. Eso
  aísla el efecto de la puntuación, pero no evalúa cambios de cobertura.
- Resultado no estricto en las tres configuraciones: posiciones sin evento
  terminal confirmado, heredadas de la serie del #35.

## Reproducibilidad

`python -m gabi.r3_experiment --preregister`, `--prepare-risk`,
`--check-control`, `--run <configuración>` y `--analyze`. Usa los rankings
congelados de `data/revalidation_2011_2025/acreditado-38`, con sus hashes y
snapshot. Los CSV de la ventana de riesgo están en `data/r3_e6/`, con su
SHA-256 en `risk756-manifest.json`.
