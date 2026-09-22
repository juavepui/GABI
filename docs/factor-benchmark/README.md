# Benchmark ajustado por beta y factores

Implementación del [issue #16](https://github.com/juavepui/GABI/issues/16),
2026-09-22. Se incorporan curvas de riqueza contra **SPY ajustado por beta** y
**FF5+Momentum sin alfa**, junto a estrategia, SPY sin ajustar, RF y universo
equal-weight. Todas las referencias se comparan sobre las mismas fechas.

## Qué mide cada referencia

Se estima por OLS con intercepto:

```text
Estrategia − RF = alfa + beta_SPY * (SPY − RF) + residuo
Benchmark beta = RF + beta_SPY * (SPY − RF)
              = beta_SPY * SPY + (1 − beta_SPY) * RF

Estrategia − RF = alfa + suma(beta_j * factor_j) + residuo
Benchmark factores = RF + suma(beta_j * factor_j)
```

El intercepto se estima para calcular correctamente las betas, pero **no se
añade a las curvas benchmark**. Añadirlo incorporaría precisamente el retorno
que se desea evaluar. Para beta=0,97, la primera referencia sería 97% SPY y
3% RF. La implementación estima beta con los inputs concretos, sin fijar el
0,97 histórico ni imponer beta entre cero y uno.

El benchmark SPY usa los retornos de SPY de las mismas ventanas del backtest.
No sustituye SPY por `Mkt-RF`: este último es el exceso del mercado amplio
ponderado por valor de CRSP, según la
[definición de Kenneth French](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/f-f_5_factors_2x3.html).
La beta univariante frente a SPY y la beta parcial de mercado condicionada a
otros cinco factores no son la misma magnitud.

Las betas pueden implicar posiciones cortas o apalancamiento. RF se utiliza
como rentabilidad de caja y coste de financiación idealizado. No se añaden
spreads de financiación, préstamo de títulos, costes de replicación ni impuestos.
Los factores académicos long-short no son seis ETFs directamente invertibles.
La estrategia conserva los costes incluidos en los retornos V1.

Un exceso sobre estas referencias **no demuestra causalmente selección de
valores**: puede incluir factores omitidos, timing, ruido, costes y sesgos de
datos. Es una comparación de exposiciones, no una separación perfecta de causas.

## Dos protocolos, sin confundir atribución y evaluación temporal

**In-sample:** estima betas con los 36 trimestres y construye las referencias
para esos mismos 36. Incluye información futura respecto a cada periodo y se
etiqueta como atribución retrospectiva. Conserva la inferencia HAC del intercepto
de la regresión completa.

**Expansivo:** mínimo de 18 trimestres de entrenamiento; para evaluar la fila
`t`, se entrena con filas `0..t−2`, dejando `t−1` fuera. Ese trimestre de embargo
evita usar inmediatamente el periodo recién terminado para factores que se
publican con retraso. Además se exige que el último retorno de entrenamiento
termine antes de la fecha de decisión evaluada. Las betas no usan el retorno
objetivo ni los posteriores; los factores/SPY realizados del periodo evaluado
determinan el resultado contemporáneo del benchmark, no sus betas.

Con 36 observaciones, la primera evaluación es abril de 2021 y quedan
**17 trimestres hasta julio de 2025**. Cada protocolo reinicia todas las curvas
en 1 en su propio inicio. No se rellenan los 19 trimestres iniciales con ceros
ni se compara la estrategia completa contra un benchmark de historia más corta.
Los 18 trimestres y el embargo se fijaron para este diagnóstico; no se eligieron
optimizando la ventaja observada.

Este protocolo sigue siendo retrospectivo: los factores descargados incorporan
revisiones y no hay vintages históricos que acrediten su disponibilidad exacta.
El embargo no elimina eso ni la selección previa de estrategia y modelos sobre
el mismo histórico. No se presenta como validación prospectiva ni se estima
un t-stat de «selección» sobre los excesos expansivos.

## Resultado sobre los inputs reconstruidos

Se reutilizan los 36 inputs de la [auditoría HAC](../academic-factors-hac.md)
y se añaden SPY/universo EW de los mismos periodos V1 guardados en
`data/hac_audit_periods.csv`. Se verificaron fechas y retornos de estrategia
antes de publicar la unión en [inputs.csv](inputs.csv). Así se repite el análisis
sin acceso a la base privada.

Configuración: Top-20 trimestral, N=200 por fecha, semilla 42, pesos 30/35/25/10,
10 pb por lado, julio de 2016 a julio de 2025. No se modifica la estrategia.
Persisten las limitaciones de identidad y universo muestreado.

La beta actual frente a SPY es **1,03546**, no 0,97. Su alfa trimestral es
0,51466% (anualizado geométricamente 2,07458%), t HAC **0,99172**. La beta
parcial `Mkt-RF` de FF5+Mom es 1,04607; su alfa anualizado sigue siendo 2,40576%,
t HAC 1,15962, como en el recálculo anterior. No se afirma que sean los mismos
inputs que produjeron las cifras históricas originales.

| Curva | CAGR in-sample, 36 trimestres | CAGR expansivo, 17 trimestres |
|---|---:|---:|
| Estrategia | **17,83%** | **14,66%** |
| SPY | 15,23% | 13,57% |
| SPY ajustado por beta | 15,65% | 13,98% |
| FF5+Momentum sin alfa | 15,27% | 15,27% |
| Universo EW | 13,94% | 10,77% |
| RF | 2,10% | 3,22% |

| Comparación | Diferencia de CAGR in-sample | Diferencia de CAGR expansiva |
|---|---:|---:|
| Estrategia − SPY ajustado | +2,18 pp/año | **+0,68 pp/año** |
| Estrategia − FF5+Momentum | +2,56 pp/año | **−0,61 pp/año** |

En la evaluación expansiva, el exceso de riqueza acumulada es +2,54% frente
a SPY ajustado y −2,22% frente a FF5+Momentum. El exceso aritmético medio por
trimestre es +0,0591% y −0,2300%, respectivamente. No son alfas de una regresión
con coeficientes constantes ni p-valores. El cambio entre protocolos también
cambia el periodo evaluado: no aísla exclusivamente el efecto de estimar betas
sin datos futuros.

El resultado no sostiene una ventaja uniforme frente a exposiciones conocidas:
con estimación previa, la estrategia queda ligeramente por debajo del benchmark
multifactor en este tramo. Con 17 observaciones y selección retrospectiva, esto
tampoco demuestra inferioridad estadística ni ausencia de habilidad.

## Contabilidad, artefactos e interfaz

Cada curva compone los retornos reales o sintéticos del protocolo, sin sumar
porcentajes de periodos distintos. CAGR usa `capital_final**(4/n)−1`, con años
trimestrales `n/4`; se conserva la aproximación mensual a fechas bursátiles.
El exceso de riqueza es `capital_estrategia/capital_benchmark−1`. La diferencia
de CAGR no se etiqueta como alfa. En in-sample, la media aritmética del exceso
por periodo sí coincide con el intercepto OLS (porque se estimó con constante).

Se rechazan huecos mensuales, datos no finitos, matrices sin rango completo,
falta de SPY y retornos sintéticos ≤−100% que impiden construir riqueza positiva.
No se recortan betas, ni se imputan RF o meses, ni se omiten periodos inválidos.
Si no hay historia suficiente para entrenamiento y embargo, el protocolo
expansivo aparece como no disponible.

- [inputs.csv](inputs.csv): estrategia, RF, factores, SPY y universo EW.
- [audit.json](audit.json): métodos, limitaciones, regresiones, cada coeficiente
  expansivo y fechas de entrenamiento, retornos/riqueza/excesos y hashes.
- [in_sample-curves.csv](in_sample-curves.csv): curvas retrospectivas, base 1.
- [expanding-curves.csv](expanding-curves.csv): curvas comparables tras embargo.

Research Lab ofrece el informe guardado y Ranking histórico V1 genera el mismo
diagnóstico para backtests trimestrales compatibles. El selector abre por
defecto el protocolo expansivo; el retrospectivo muestra un aviso explícito.
Ambos permiten descargar curvas y resultados completos. El contraste diario
V2 no se convierte artificialmente en esta regresión trimestral.

Reproducción sin red desde la raíz:

```powershell
.venv/Scripts/python.exe -m gabi.factor_benchmark
```

El comando admite `--inputs` y `--output`. No escribe experimentos ni modifica
la prueba ciega. Las huellas son portables entre finales de línea LF/CRLF;
`load_audit()` verifica los CSV antes de mostrarlos.

## Verificación

Tests de recuperación de betas conocidas e intercepto excluido, factor RF
correcto, entrenamiento con embargo y fechas maduras, invariancia de predicciones
anteriores al cambiar retornos objetivo/futuros, capitalización y reinicio
común, muestras cortas, huecos/duplicados/NaN, SPY distinto de Mkt-RF,
benchmarks no capitalizables y reproducción de curvas/inputs congelados.

Verificación final: **579 tests correctos**, incluidos 17 de benchmarks;
Ruff y mypy (45 archivos) correctos, 44 módulos importados y 17 archivos de la
app compilados. Streamlit AppTest comprobó ambos protocolos, tablas, curvas y
el aviso retrospectivo. Los ocho avisos de pytest proceden de correlaciones
constantes en tests preexistentes de Factor Lab.
