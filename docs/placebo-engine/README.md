# STAT-6 (#49): falsificación y perturbaciones del Top-20

El [preregistro](PREREGISTRO.md), SHA-256
`2fd302ec4004550ec4080c46e8e7f0fd319ce6e3bb9c0f688134c2cae8ba29fa`,
se selló en el commit `9e30087` antes de simular. La configuración y las
huellas de los datos/código están en [resultado.json](resultado.json).
Las **8.192 trayectorias** (2.048 por control) y sus seis métricas se
publican completas en [null_distributions.csv](null_distributions.csv);
las 256 perturbaciones de pesos están en
[weight_perturbations.csv](weight_perturbations.csv).

## Resultado retrospectivo

En los 57 trimestres de #40, el Top-20 vigente produjo 19,05 % de CAGR
bruto, Sharpe 1,10, drawdown trimestral −20,51 %, ES5 trimestral −17,69 %
y exceso medio de **+1,36 puntos por trimestre** frente al universo elegible.
El exceso fue positivo en las tres ventanas predefinidas.

| Control | Mediana CAGR | P95 CAGR | Mediana exceso trimestral | p empírico del exceso | Tipo |
| --- | ---: | ---: | ---: | ---: | --- |
| Ranking aleatorio | 12,66 % | 15,20 % | +0,01 pp | 0,0010 | Aleatorización condicional |
| Top-20 aleatorio | 12,61 % | 15,21 % | +0,01 pp | 0,0005 | Aleatorización condicional |
| Top-20 con conteos sectoriales | 12,58 % | 15,23 % | 0,00 pp | 0,0005 | Aleatorización condicional, sector no identificable |
| Retornos permutados dentro de sector | 12,59 % | 15,13 % | 0,00 pp | 0,0005 | Solo diagnóstico |

Los tres controles de selección conservan los retornos observados y el shock
de mercado de cada trimestre; el tercero conservaría además la exposición
sectorial si la fuente tuviera sectores fechados. En esta muestra **todos los
sectores históricos son desconocidos**, por lo que ese control se reduce a
otro Top-20 uniforme. No aporta una prueba sectorial adicional. La
permutación de retornos no conserva trayectorias individuales y su p no se
trata como inferencia temporal plena. El ranking aleatorio y el Top-20
aleatorio también son equivalentes en distribución: sus diferencias numéricas
proceden de semillas independientes.

La inversión fija del signo (Bottom-20) baja a 12,25 % CAGR, Sharpe 0,58 y
drawdown −36,45 %. Retrasar el ranking un trimestre reduce el exceso medio a
+0,76 pp en 56 trimestres, frente a +1,37 pp de la estrategia vigente en
**esos mismos 56**. Las perturbaciones de pesos ±2,5 pp dan CAGR P5/mediana/P95
de 17,88 % / 18,90 % / 19,64 %; no se selecciona el mejor vector.

La familia fija de 257 pesos (original + 256 perturbados) se pasó a las
funciones existentes de rigor estadístico: **PBO/CSCV 0,45** con seis bloques
y **DSR 0,999**. Son diagnósticos de esa familia cercana, no una auditoría de
todas las configuraciones probadas durante el desarrollo. Un PBO de 0,45
indica que elegir por mejor desempeño dentro de esta familia sería frágil;
el DSR alto no revierte ese problema ni valida el Top-20 fuera de muestra.

**Conclusión:** el Top-20 observado supera con holgura a la selección
aleatoria condicionada al universo y los trimestres de esta reconstrucción.
Eso no distingue una señal reproducible de una configuración elegida durante
el desarrollo ni confirma ventaja futura. Ningún percentil se ha usado para
optimizar pesos o modificar Investor.

## Reproducción y reutilización

```powershell
.venv/Scripts/python.exe -m gabi.placebo_engine --analyze
.venv/Scripts/python.exe -m pytest tests/test_placebo_engine.py -q
```

`placebo_engine.simulate(panels, top_n=..., n_simulations=..., seed=...,
windows=...)` acepta paneles trimestrales de otra variante con puntuación,
retorno y sector, cada uno con `attrs["date"]`. El llamador debe preregistrar
la variante, N, ventanas, simulaciones y seed. El resultado de #49 incluye
SHA-256 del código, manifiesto, 57 rankings y 57 ficheros de retornos, además
de [la trayectoria observada por trimestre](observed_by_quarter.csv).
