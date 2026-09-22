# Inferencia Fama-French con HAC/Newey-West

Implementación del [issue #11](https://github.com/juavepui/GABI/issues/11),
2026-09-21. La revisión del resto de issues está en
[issues-review-2026-09-21.md](issues-review-2026-09-21.md).

Continuación 2026-09-22: estos mismos 36 inputs se usan en el
[análisis temporal por mitades, ventanas móviles y episodios](factor-stability/README.md).
La estimación HAC de toda la muestra no acredita estabilidad temporal.

## Qué cambia

`regress_returns_on_factors()` sigue estimando alfa y betas por OLS sobre
el exceso de retorno respecto a RF. Cambia la estimación de incertidumbre:
los campos `se` y `t_stat` usan HAC/Newey-West para todos los coeficientes.
`se_ols` y `t_stat_ols` conservan el diagnóstico homocedástico anterior.
Ni los coeficientes ni R² cambian al elegir otro número de retardos.

La implementación usa NumPy, sin una dependencia nueva. Para residuos
`u_t`, filas de diseño `x_t` (incluido el intercepto), `z_t=x_t*u_t` y
`B=(X'X)^(-1)`, calcula:

```text
S = sum(z_t z_t')
    + sum_{l=1..L} (1-l/(L+1)) * sum_{t=l..n-1}(z_t z_{t-l}' + z_{t-l} z_t')
Cov_HAC = (n/(n-k)) * B S B
SE_j = sqrt(Cov_HAC[j,j])
t_j = coef_j / SE_j
```

`k` incluye alfa. El inverso se obtiene a partir de la pseudoinversa de X,
evitando formar/invertir X'X para calcularlo. Se rechazan diseños sin rango
completo, datos no finitos y muestras sin grados de libertad residuales.

El kernel es Bartlett; la corrección de muestra pequeña es `n/(n-k)`.
Por defecto `L=floor(4*(n/100)^(2/9))`, limitado a `n-1`: **3 retardos para
36 observaciones**. Es la convención de
[`statsmodels.stats.sandwich_covariance.cov_hac`](https://www.statsmodels.org/stable/generated/statsmodels.stats.sandwich_covariance.cov_hac.html)
con `use_correction=True`. `hac_lags=0` corresponde a HC1, sin autocovarianzas;
no recupera los errores homocedásticos.

```python
from gabi import academic_factors

reg = academic_factors.regress_returns_on_factors(periods, factors)
print(reg["hac_lags"], reg["t_stat"]["alpha"], reg["t_stat_ols"]["alpha"])
# Sensibilidad predefinida: cuatro trimestres, sin elegir según el resultado.
reg_l4 = academic_factors.regress_returns_on_factors(periods, factors, hac_lags=4)
```

Un retardo es un **periodo de retorno**, no un mes. El API ordena las
observaciones por fecha y exige ventanas mensuales consecutivas de igual
duración; no comprime huecos interiores ni acepta duplicados/solapamientos
de esas ventanas. Los retardos explícitos deben ser enteros entre 0 y n−1.
El alfa se anualiza con `12/meses_por_periodo`, corrigiendo también el
exponente trimestral fijo que antes se usaba con frecuencias semestrales.

Ranking histórico muestra t-stats HAC para alfa y betas, los errores
estándar HAC de las betas, el t-stat OLS del alfa como comparación y el
criterio de retardos/corrección. Un desplegable permite fijar L.

## Interpretación y límites

HAC puede aumentar **o reducir** el error estándar: no se fuerza a que el
t-stat sea menor. Las ventanas solapadas de las señales motivan comprobar
autocorrelación, pero no demuestran por sí solas su signo en los residuos.

Con 36 observaciones y 7 coeficientes quedan 29 grados de libertad.
La corrección de muestra pequeña no convierte HAC en una prueba exacta:
los umbrales aproximados de t no son una garantía de significancia. HAC
tampoco corrige selección de modelos, multiple testing ni sesgos de datos.
Los retardos deben elegirse antes de evaluar significancia; la sensibilidad
se reporta completa, sin seleccionar el L con el resultado preferido.

Se conserva la composición mensual de los factores y RF del módulo
original. Es una aproximación a las fechas efectivas de compra/venta del
backtest, que usa sesiones bursátiles. Esta entrega no cambia esa
alineación, el proveedor ni el tratamiento existente de meses parciales
o RF ausente; HAC no remedia esas limitaciones de los inputs.

El t-stat histórico **1,61** (y el semestral 0,62) fue calculado sin HAC.
README e HIPOTESIS_CONGELADA lo identifican ahora expresamente. Los
experimentos antiguos no guardaron las series de retornos originales:
un recálculo con la caché actual no se puede presentar como una corrección
exacta de aquellos inputs.

## Recálculo con la caché actual — 2026-09-21

Motor V1, Top-20 trimestral, 2016-07-02 a 2025-07-02, muestra de 200
empresas por periodo (semilla 42), pesos 30/35/25/10, coste de 10 pb por
lado, sin banda de permanencia. Completó **36/36 periodos**, sin omisiones,
en unos 20 minutos. Es un análisis RESEARCH sobre universo muestreado y
con la lectura no estricta de identidad existente, no validación prospectiva.

| Magnitud | OLS convencional | HAC, L=3 |
|---|---:|---:|
| Alfa trimestral | +0,5961% | +0,5961% |
| Alfa anualizado | +2,4058% | +2,4058% |
| Error estándar del alfa trimestral | 0,7051 puntos porcentuales | 0,5140 puntos porcentuales |
| t-stat del alfa | **0,8454** | **1,1596** |
| R² | 0,8873 | 0,8873 |

En esta serie, HAC **aumenta** el t-stat del alfa. La autocorrelación
muestral de primer orden de los residuos es −0,1253, no positiva; no es
una prueba de ausencia de dependencia ni determina por sí sola toda la
covarianza HAC. El alfa sigue lejos de los umbrales habituales: esta
corrección no aporta evidencia suficiente para afirmar alfa distinto de cero.

Sensibilidad completa al retardo, sin seleccionar el resultado favorable:

| L (trimestres) | t-stat HAC del alfa |
|---:|---:|
| 0 (HC1) | 0,8823 |
| 1 | 0,9420 |
| 2 | 1,0198 |
| **3 (automático)** | **1,1596** |
| 4 | 1,2752 |

**El OLS de este recálculo es 0,8454, no el 1,61 histórico.** También
cambiaron alfa y R² respecto a la tabla antigua, antes de aplicar HAC.
Sin los inputs originales no puede atribuirse la diferencia a una causa
concreta ni afirmarse que «HAC corrigió 1,61 a 1,16». La comparación válida
que aísla el efecto de HAC es **0,8454 → 1,1596 sobre la misma serie actual**.

## Verificación

31 tests de factores académicos: cálculo manual de un intercepto,
covarianza mediante una formulación independiente con matriz Bartlett
densa (seis factores, n=36, L=0/1/3/4/35), residuos persistentes,
invariancia de coeficientes/R², orden temporal, frecuencia de anualización,
retardos inválidos, matrices singulares y huecos de calendario.

Suite completa: 478 tests; Ruff, mypy, importación de 38 módulos y
compilación de 17 archivos de la app correctos. Los ocho avisos de pytest
proceden de correlaciones con inputs constantes en tests de Factor Lab.

## Reproducir la inferencia del recálculo

El [CSV de inputs](academic-factors-hac-inputs.csv) conserva las ventanas,
retornos, RF y seis factores ya compuestos usados en el recálculo. El
[JSON de resultados](academic-factors-hac-audit.json) conserva parámetros,
huellas de inputs/código y sensibilidad. Permiten repetir **la regresión**
sin descargar datos ni reconstruir el ranking; no sustituyen una copia de
la base point-in-time necesaria para repetir todo el backtest.

Desde la raíz del proyecto:

```python
import json
from pathlib import Path
import numpy as np
import pandas as pd
from gabi import academic_factors as af

inputs = pd.read_csv("docs/academic-factors-hac-inputs.csv")
audit = json.loads(Path("docs/academic-factors-hac-audit.json").read_text())
names = ["alpha"] + af.DEFAULT_FACTOR_COLS
X = np.column_stack([np.ones(len(inputs)), inputs[af.DEFAULT_FACTOR_COLS]])
reg = af._ols(inputs["excess_return"].to_numpy(), X, names)
np.testing.assert_allclose(
    list(reg["t_stat"].values()), list(audit["regression"]["t_stat"].values()),
    rtol=1e-10, atol=1e-12,
)
print(reg["t_stat_ols"]["alpha"], reg["t_stat"]["alpha"])
```
