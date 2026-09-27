# STAT-5 (#48): mapa de evidencia por señal

El [preregistro](PREREGISTRO.md), SHA-256
`fdf6e429282e7c70ed9ae5c8ac7997bbdbb39b55d8675324eaef9586f6017e59`,
se selló en el commit `4005129` antes de este análisis. Los resultados
reproducibles están en [resultado.json](resultado.json),
[factor_summary.csv](factor_summary.csv), [factor_ic.csv](factor_ic.csv),
[quantile_returns.csv](quantile_returns.csv), [stability.csv](stability.csv) y
[correlations.csv](correlations.csv). La tabla
[factor_lab_summary.csv](factor_lab_summary.csv) usa los nombres de columnas
de resumen de Factor Lab y añade la inferencia de #48.

## Resultado

**Ninguna de las 13 señales supera Holm al 5 %.** Todas se han medido sobre
los mismos 57 trimestres y retornos futuros de #40. `EV/EBITDA` y `PER` tienen
los mayores IC medios positivos, pero sus `p` ajustadas son 0,202 y 0,266.
Señales de momentum y deuda aparecen con IC medio negativo. Las clasificaciones
son retrospectivas; ninguna es validación independiente.

| Familia | Señal | IC medio | t HAC | ICIR | Spread Q5−Q1 | p Holm | Clasificación |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| Value | `pe` | +0,034 | 2,06 | 0,248 | +0,98 pp | 0,266 | indicio |
| Value | `pb` | +0,013 | 0,74 | 0,101 | +0,88 pp | 1,000 | indicio |
| Value | `ev_ebitda` | +0,038 | 2,21 | 0,265 | +1,16 pp | 0,202 | indicio |
| Quality | `roic` | +0,013 | 0,96 | 0,116 | +0,42 pp | 1,000 | indicio |
| Quality | `operating_margin` | −0,007 | −0,48 | −0,070 | −0,82 pp | 1,000 | sin evidencia |
| Quality | `revenue_cagr_3y` | −0,004 | −0,25 | −0,034 | +0,11 pp | 1,000 | sin evidencia |
| Quality | `fcf_cagr_3y` | +0,010 | 0,77 | 0,102 | +0,53 pp | 1,000 | indicio |
| Momentum | `momentum_12m` | −0,014 | −0,55 | −0,072 | −0,79 pp | 1,000 | sin evidencia |
| Momentum | `rel_strength_6m` | −0,004 | −0,18 | −0,025 | −0,10 pp | 1,000 | sin evidencia |
| Momentum | `price_vs_sma200` | −0,012 | −0,60 | −0,071 | −0,26 pp | 1,000 | sin evidencia |
| Risk | `debt_to_equity` | −0,022 | −1,73 | −0,220 | −1,09 pp | 1,000 | sin evidencia |
| Risk | `volatility` | +0,004 | 0,12 | 0,015 | −0,94 pp | 1,000 | indicio |
| Risk | `max_drawdown` | +0,006 | 0,20 | 0,025 | −0,65 pp | 1,000 | indicio |

Las ventanas fijas de `EV/EBITDA` tienen IC +0,036, +0,001 y +0,079;
las de `PER`, +0,032, +0,014 y +0,058. Esto no corrige el resultado global
ni permite elegir la mejor ventana. En los terciles de capitalización, el IC
de `PER` es −0,002 (grandes), +0,030 (medianas) y +0,052 (pequeñas).

La [matriz de correlación](correlations.csv) muestra redundancias fuertes:
`rel_strength_6m` con `price_vs_sma200` (ρ medio 0,92), `pe` con
`ev_ebitda` (0,81) y `volatility` con `max_drawdown` (0,75). Las 13 pruebas
se mantuvieron en Holm tal como estaban declaradas; estas correlaciones no
se usan para reducir a posteriori el número de contrastes.

## Límite sectorial

Los rankings históricos congelados tienen la columna `sector` vacía. La base
auxiliar solo tiene fotografías sectoriales de **2026-09-18**, posteriores a
todos los retornos evaluados. Usarlas como si fueran sectores de 2011–2025
introduciría información futura y sesgo de supervivencia. Por ello
`stability.csv` contiene el análisis por tamaño, pero **la estabilidad por
sector no es estimable con estos datos**. Las pendientes Fama-MacBeth incluyen
el control de capitalización; la categoría de sector ausente es única y no
equivale a un control sectorial efectivo. Este criterio del issue queda
pendiente de una fuente histórica de sectores fechada.

## Reproducción

```powershell
.venv/Scripts/python.exe -m gabi.factor_zoo --analyze
.venv/Scripts/python.exe -m pytest tests/test_factor_zoo.py tests/test_cross_section_test.py -q
```

El resultado almacena el hash de la especificación, código, manifiesto, 57
rankings y 57 ficheros de retornos. No se han seleccionado factores por CAGR
de Top-N ni se han modificado los pesos del Composite.
