# VaR, Expected Shortfall y forma de la distribución

Implementación del [issue #15](https://github.com/juavepui/GABI/issues/15),
2026-09-22. `portfolio_metrics.py` incorpora VaR/ES históricos al 95% y 99%,
asimetría y exceso de curtosis. Las métricas describen retornos de **una
observación de la serie de entrada**, sin anualización ni hipótesis normal.

## Convenciones

Se trabaja con pérdidas `L = −retorno`, en fracciones: 0,02 significa una
pérdida del 2%. Un resultado negativo significa ganancia incluso en la cola
observada; no se recorta a cero.

**VaR** usa la inversa de la distribución empírica, sin interpolación entre
pérdidas: para n observaciones equiprobables, la pérdida ordenada de posición
`ceil(n * confianza)` (posición inicial 1). Es un umbral, no una pérdida máxima
posible ni una garantía sobre el próximo periodo.

**Expected Shortfall (ES/CVaR)** promedia exactamente la masa `1−confianza` de
peores pérdidas. Ordenando pérdidas de mayor a menor, con `m=n*(1−confianza)`,
`k=floor(m)` y `f=m−k`:

```text
ES = (sum(primeras k pérdidas) + f * pérdida siguiente) / m
```

La frontera fraccionaria importa con muestras pequeñas y empates. Por ejemplo,
con 30 observaciones y pérdidas máximas del 20% y 10%, ES95 promedia una
observación y media: `(20% + 0,5*10%)/1,5 = 16,67%`. No es la media simple
del 15% ni la media de todas las pérdidas mayores o iguales a un cuantil
interpolado. La definición admite masas discretas como desarrolla
[Rockafellar y Uryasev](https://sites.math.washington.edu/~rtr/papers/rtr187-CVaR2.pdf).

**Asimetría** es Fisher-Pearson ajustada por tamaño de muestra (n≥3); signo
negativo indica asimetría de los retornos hacia la izquierda. **Curtosis** se
presenta como exceso Fisher corregido (n≥4): la referencia normal es **0**, no
3. Son las convenciones `bias=False` de
[SciPy skew](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.skew.html)
y [kurtosis, fisher=True](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.kurtosis.html).
No se usa la convención Pearson=3 de los momentos empleados en PSR/DSR ni se
cambia ese código. Las correcciones finitas no eliminan dependencia temporal.

## Resolución muestral y validación de datos

Se conservan `n_obs`, `tail_mass=n*(1−confianza)` y `tail_observations` (número
de filas con peso positivo, incluida la frontera). No cuentan eventos
independientes. La interfaz indica:

- `empty`: sin observaciones; VaR/ES y momentos no disponibles.
- `below_resolution`: masa de cola <1; VaR y ES coinciden con la peor pérdida.
- `sparse`: masa entre 1 y menos de 5 observaciones equivalentes.
- `descriptive`: masa ≥5; **no** implica precisión garantizada ni validación.

Cinco observaciones es una regla de aviso elegida para la interfaz, no un
umbral estadístico de suficiencia. Los momentos de una serie constante son
indefinidos (`None`), mientras VaR/ES siguen estando definidos.

NaN, infinitos y arrays de más de una dimensión se rechazan; no se eliminan
silenciosamente. `returns_from_nav()` usa diferencias simples sin forward-fill
y no añade un cero inicial. Rechaza fechas duplicadas/desordenadas/ausentes,
NAV negativos o divisores cero; admite una pérdida total terminal. El llamante
declara la frecuencia: la función no reconstruye sesiones que falten ni certifica
por sí sola el calendario bursátil. No corrige precios imputados anteriormente
por el motor de valoración.

Las distribuciones individuales usan los retornos disponibles de cada cartera,
con su propio n. Estas métricas no dependen de alinear un benchmark, pero antes
de comparar cifras debe comprobarse que cubren el mismo horizonte y rango.

## Aplicación a los ensayos guardados

Se han calculado las métricas para **las 24 series de 36 trimestres** de la
[auditoría PBO/DSR](overfitting-audit/README.md). Se conservan en
[tail-risk-audit.json](tail-risk-audit.json), con huella de la matriz y del
código. No se selecciona una nueva variante por su ES.

Para el Top-20 trimestral, sobre la misma reconstrucción V1 N=200, semilla 42,
2016-07 a 2025-07, pesos 30/35/25/10 y 10 pb por lado:

| Métrica | Resultado por trimestre |
|---|---:|
| VaR 95% | 12,0577% |
| ES/CVaR 95% | 18,6501% |
| VaR 99% | 23,9240% |
| ES/CVaR 99% | 23,9240% |
| Asimetría de retornos | −0,2289 |
| Exceso de curtosis | +1,5784 |

**ES95 solo usa 1,8 observaciones equivalentes; ES99 usa 0,36.** El dato del
99% es la peor pérdida trimestral observada y no resuelve un extremo distinto.
Estas cifras no son riesgo diario, no capturan una caída y recuperación dentro
del trimestre y no sustituyen el drawdown. Tampoco demuestran por sí solas
normalidad/no normalidad o calibración de probabilidades futuras. Persisten las
limitaciones de universo muestreado e identidad de la reconstrucción V1.

## Interfaz y uso

- Ranking histórico V1: estrategia, universo EW y SPY, con duración del periodo
  derivada de los datos guardados, no de los controles actuales del formulario.
  No mezcla periodos de duración diferente ni imputa periodos saltados.
- Ranking histórico V2: estrategia y SPY sobre NAV diario.
- Portfolio Lab: esquemas de ponderación y SPY sobre NAV diario.
- Research Lab: selector de experimentos que tienen retornos guardados; usa la
  frecuencia registrada (sin convertirla). Los experimentos con solo métricas
  resumen no ofrecen un VaR/ES inventado.

Cada vista muestra tamaño y masa de cola, avisos y descarga JSON. Se calculan
al visualizar las series; no requiere migración de base de datos ni modifica
experimentos históricos o validaciones ciegas.

```python
from gabi import portfolio_metrics as pm

returns = pm.returns_from_nav(nav_diario)
metrics = pm.tail_risk_metrics(returns, horizon="una sesión")
var95 = pm.historical_var(returns, confidence=.95)
es99 = pm.expected_shortfall(returns, confidence=.99)
```

Reproducir las 24 distribuciones del informe desde la raíz, sin red ni base
privada:

```python
import json
from pathlib import Path
import numpy as np
from gabi import overfitting_audit, portfolio_metrics

_, matrix = overfitting_audit.load_audit(Path("docs/overfitting-audit"))
saved = json.loads(Path("docs/tail-risk-audit.json").read_text(encoding="utf-8"))
for name in matrix:
    result = portfolio_metrics.tail_risk_metrics(matrix[name], horizon="un trimestre")
    for level in ("95", "99"):
        for metric in ("var", "expected_shortfall"):
            np.testing.assert_allclose(
                result[level][metric], saved["summaries"][name][level][metric],
                rtol=1e-10, atol=1e-12,
            )
print(saved["summaries"]["top20_q"])
```

## Verificación

Pruebas de cálculo manual de cuantiles y colas enteras/fraccionarias, empates,
coincidencia con la formulación independiente de minimización de CVaR,
invariancia al orden, traslación y escalado, y monotonía por confianza. Los
momentos se contrastan con SciPy; se prueban muestras cortas/constantes,
NaN/inf, NAV inválidas y reproducción de las 24 series publicadas.

Verificación final: **562 tests correctos** (48 en `test_portfolio_metrics.py`),
Ruff y mypy correctos, 42 módulos importados y 17 archivos de la app compilados.
Streamlit AppTest comprobó la vista de retornos trimestrales, los dos avisos
de cola escasa/sin resolución y la vista de NAV diario sin excepciones.
Los ocho avisos de pytest corresponden a correlaciones constantes en tests
preexistentes de Factor Lab.
