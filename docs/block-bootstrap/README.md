# STAT-7 (#50): distribución de incertidumbre

Research Lab muestra ahora intervalos, histogramas y sensibilidad temporal
para CAGR, volatilidad, Sharpe, drawdown, ES5 y diferencias emparejadas frente
a un benchmark. La aplicación permite calcular el diagnóstico de experimentos
con retornos guardados y frecuencia explícita, y descargar parámetros y
réplicas completas. También muestra esta auditoría ya calculada.

El [protocolo](PREREGISTRO.md) se registró en `e21c83b`, antes de ejecutar
el análisis; [preregistro.json](preregistro.json) tiene SHA-256 canónico
`2dfbca638cb4cbeedcdb5bf0ad62f0e796548143c1aa6a174cb9e6c0e08a9c96`.
El código de cálculo publicado corresponde a `8a75a76`. El
[resultado completo](resultado.json) contiene huellas de datos y código,
versiones de Python y dependencias, configuración y las tres longitudes de
bloque. Las entradas son archivos previamente publicados: no se descargaron
datos ni se volvieron a ejecutar los backtests, ni se alteraron #44 o sus
reglas de congelación.

## V2 Top-20 neto frente al SPY

3.584 sesiones, desde 2011-07-05 hasta 2025-10-02, misma ventana para ambas
series. Se incluyó el retorno de la primera sesión a partir del NAV anterior,
con sus costes. 4.096 réplicas por longitud; seed 500050. Tipo libre de riesgo
0; CAGR por frecuencia 252 y Sharpe/volatilidad con convención sqrt(252).
Estas convenciones pueden diferir de otras tablas históricas de GABI.

Con el bloque principal de 20 sesiones:

| Métrica GABI | Observado | Rango percentil 95 % |
|---|---:|---:|
| CAGR anual | 18,87 % | 8,39 % a 30,04 % |
| Volatilidad anual | 19,32 % | 16,75 % a 22,28 % |
| Sharpe anual | 0,992 | 0,499 a 1,531 |
| Drawdown máximo | −32,81 % | −50,80 % a −18,71 % |
| ES5 diario, pérdida | 2,90 % | 2,46 % a 3,42 % |

El SPY tiene CAGR observado 13,99 %. La **diferencia de CAGR** es
**+4,88 puntos anuales**, con rango **−0,10 a +9,88 puntos**; incluye cero.
La diferencia de Sharpe es +0,151, con rango −0,083 a +0,365.

El exceso medio diario es +0,0181 puntos; su rango bootstrap es
+0,00108 a +0,03454 puntos y el HAC es +0,00112 a +0,03504 puntos, con
8 retardos. Ambos excluyen cero para **esa media**, pero no permiten declarar
una ventaja robusta en CAGR ni validar una configuración elegida durante
el desarrollo.

| Bloque, sesiones | Rango de diferencia de CAGR, puntos anuales |
|---|---:|
| 20, principal | −0,10 a +9,88 |
| 10, sensibilidad | −0,01 a +10,15 |
| 40, sensibilidad | +0,17 a +9,68 |

El cambio del extremo inferior con 40 sesiones muestra dependencia del
método; no se selecciona esa longitud para afirmar significación. HAC y
bootstrap coinciden al excluir cero del exceso medio para las tres
longitudes.

97,27 % de las réplicas tienen CAGR mayor que SPY; 90,70 % tienen Sharpe
mayor. Son **fracciones bootstrap condicionadas al histórico**, no p-valores
ni probabilidades de ganar en el futuro. En 95,63 % de las trayectorias
GABI el drawdown alcanza una pérdida del 20 %: el horizonte es **la duración
completa remuestreada**, unos 14 años, no un año ni una predicción.

Distribución completa: [v2_daily_net-distributions.csv](v2_daily_net-distributions.csv).
Intervalos: [v2_daily_net-intervals.csv](v2_daily_net-intervals.csv).

## Medias temporales del IC y del spread

57 trimestres de #40, 2011-07 a 2025-07, sin tratar empresas como fechas
independientes. Bloque principal de 4 trimestres, sensibilidad 2/8.

| Estadístico | Observado | Percentil 95 %, bloque 4 | HAC 95 % |
|---|---:|---:|---:|
| Media Rank IC | 0,00949 | −0,01861 a +0,03770 | −0,01870 a +0,03768 |
| Spread medio Q5−Q1, puntos/trimestre | +0,146 | −0,850 a +1,147 | −0,874 a +1,167 |

Se reutiliza Newey-West/Bartlett de `academic_factors._ols`, con 3 retardos y
corrección de muestra pequeña. Ambos métodos y todas las longitudes incluyen
cero. No aparece evidencia nueva de que el Composite ordene las empresas.

Distribución: [cross_section_means-distributions.csv](cross_section_means-distributions.csv).
Intervalos: [cross_section_means-intervals.csv](cross_section_means-intervals.csv).

## Serie V1 no estimable sin unir huecos

La entrada V1 prevista contiene 55 trimestres y omite 2019-10 por falta de
precio de NKTR, ya documentado en #35. También falta el periodo extremo
2025-07 por JNPR. No se concatenan 2019-07 y 2020-01 como fechas vecinas,
ni se inventa un trimestre ni se escoge otro corte. El resultado incluye
`unavailable_datasets.v1_quarterly_net` y la UI muestra el motivo. La
validación rechaza una entrada desalineada igualmente en cálculos manuales.
La V2 diaria sí conserva sesiones consecutivas y admite el diagnóstico.

## Reproducción y límites

```powershell
.venv/Scripts/python.exe -m gabi.block_bootstrap --analyze
.venv/Scripts/python.exe -m pytest tests/test_block_bootstrap.py tests/test_block_bootstrap_ui.py -q
```

`analyze_returns` acepta una matriz de retornos simples completos y
frecuencia declarada, con estrategia y varios benchmarks emparejados.
`analyze_means` acepta IC/spreads ya agregados temporalmente.
`analyze_sensitivity` ejecuta todas las longitudes fijadas. No se eliminan
NaN, ni se rellenan fechas o se intersectan ventanas silenciosamente.
Las fechas diarias se contrastan con XNYS; los periodos mensuales y
trimestrales deben ser consecutivos. Un RangeIndex declara una matriz ya
equiespaciada, responsabilidad del llamador.

Un Sharpe no estimable se conserva como ausente, con conteos de réplicas
válidas; la trayectoria mantiene sus otras métricas. ES integra exactamente
la masa fraccionaria del 5 % de pérdidas, coherente con `portfolio_metrics`.
Los rangos de drawdown/ES son descriptivos y dependen de eventos observados.
El remuestreo conserva dependencia local, rompe las uniones y supone
estacionariedad aproximada; no crea regímenes ni colas nuevos ni corrige
multiple testing o selección retrospectiva. **No constituye evidencia OOS.**

Método: [bootstrap circular temporal de arch](https://bashtage.github.io/arch/bootstrap/timeseries-bootstraps.html).
Las longitudes afectan la precisión; nuestros horizontes económicos son
decisiones prácticas fijadas, no longitudes óptimas estimadas de
[Nordman y Lahiri (2014)](https://arxiv.org/abs/1403.3275).

Validación: **890 pruebas** de la suite completa, además de la nueva prueba
de presentación de IC/spread; los módulos nuevos pasan ruff y mypy, y todos
los módulos se importan y la app compila. La revisión global encontró tres
errores de orden de imports y 25 errores de tipos **preexistentes** en
`factor_zoo`, `placebo_engine` y `tail_effect_test`, sin cambios respecto al
HEAD anterior a #50. No se modificó su código preregistrado para limpiarlos.
