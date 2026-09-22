# Estabilidad temporal de FF5 + Momentum

Auditoría retrospectiva del [issue #13](https://github.com/juavepui/GABI/issues/13),
2026-09-22. **El alfa agregado no describe un resultado uniforme en el tiempo.**
Hay cambios de signo y sensibilidad a la ventana; estos datos no demuestran
por sí solos una ruptura estructural, factor timing o decay.

Se reutilizan exactamente los 36 trimestres de la
[auditoría HAC](../academic-factors-hac.md): V1 Top-20, 2016-07 a 2025-07,
universo muestreado N=200, semilla 42, pesos 30/35/25/10, coste 10 pb/lado.
No se reconstruye otra cartera ni se revela información de la prueba ciega.
La regresión completa reproduce alfa anualizado **+2,4058%**, t HAC **1,1596**
y R² **0,8873**. No son los inputs originales del antiguo t-stat 1,61.

## Mitades cronológicas

El corte mecánico divide la muestra en dos mitades disjuntas de 18 trimestres,
sin buscar la fecha que maximice la diferencia. Las fechas indicadas abajo son
límites mensuales; los CSV conservan las fechas bursátiles originales.

| Muestra | n / g.l. | Alfa anualizado | t alfa HAC | Beta mercado | SMB | HML | RMW | CMA | Mom |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Completa, jul-2016 → jul-2025 | 36 / 29 | +2,41% | 1,16 | 1,046 | 0,069 | 0,118 | 0,180 | 0,136 | −0,053 |
| Primera, jul-2016 → ene-2021 | 18 / 11 | −2,91% | −0,83 | 1,203 | −0,378 | −0,033 | −0,031 | −0,035 | −0,310 |
| Segunda, ene-2021 → jul-2025 | 18 / 11 | +2,65% | 0,64 | 1,081 | 0,225 | 0,352 | 0,135 | −0,036 | −0,015 |

El alfa cambia de signo y las exposiciones estimadas a tamaño, value y momentum
cambian. Ambos intervalos puntuales del alfa contienen cero. La incertidumbre de
las betas es amplia: por ejemplo, los IC HAC de SMB son aproximadamente
[−1,19; 0,44] y [−0,12; 0,57]. Una beta significativa en un tramo y no en otro
no prueba que la diferencia entre ambas sea significativa. No se calcula un
p-valor de ruptura ni se interpreta la falta de significancia como estabilidad.

El alfa completo tampoco tiene por qué ser el promedio de los dos alfas: las
betas se vuelven a estimar y cambia la distribución de factores.

## Ventanas móviles

Se fijan para este diagnóstico 16, 20 y 24 trimestres (4, 5 y 6 años), paso de
un trimestre. Son decisiones retrospectivas, no una hipótesis pre-registrada.
Se publican **todos los 51 ajustes**, sin escoger el más favorable.

| Ventana | Ajustes | Rango de alfa anualizado | Rango de t alfa HAC |
|---|---:|---:|---:|
| 16 trimestres | 21 | −5,49% a +9,16% | −1,13 a +2,20 |
| 20 trimestres | 17 | −1,72% a +7,12% | −0,30 a +2,37 |
| 24 trimestres | 13 | +1,95% a +5,61% | +0,61 a +1,99 |

HAC usa Bartlett, corrección n/(n−k) y la misma regla automática que el módulo
académico, aplicada al tamaño de cada ventana: L=2 para 16/18/20/24 observaciones,
L=3 para 36. Los intervalos publicados son **coeficiente ±1,96 SE HAC**, puntuales
y asintóticos, con alfa expresado por trimestre. No son bandas simultáneas.
Las ventanas se solapan y sus t-stats no constituyen 51 confirmaciones
independientes. El máximo 2,37 no acredita alfa tras selección/múltiples pruebas.

La regresión móvil vuelve a ajustar cada ventana, siguiendo la definición de
[RollingOLS](https://www.statsmodels.org/stable/examples/notebooks/generated/rolling_ls.html).
No usa observaciones posteriores al final de esa ventana. La covarianza HAC
requiere una secuencia temporal equiespaciada, como indica la
[documentación de cov_hac](https://www.statsmodels.org/stable/generated/statsmodels.stats.sandwich_covariance.cov_hac.html).

## Episodios cortos y concentración

Con seis factores e intercepto hacen falta más de siete observaciones para
estimar varianza residual. Cada año aislado solo aporta cuatro; 2023–2024 aporta
ocho y dejaría un único grado de libertad. Se exige un mínimo prudencial de
**14 observaciones** para ajustes locales. Es una regla de presentación, no un
umbral que garantice inferencia fiable. Los cuatro episodios aparecen como
`insufficient_data`: no se publican falsos alfas/betas locales.

Las etiquetas describen años completos: 2020 incluye desplome y recuperación,
y 2018 no significa exclusivamente el selloff de Q4. Los límites mensuales son
[2018-01, 2019-01), [2020-01, 2021-01), [2022-01, 2023-01) y
[2023-01, 2025-01). Solo entran trimestres íntegramente contenidos; el resto de
filas se conserva en «Resto». No se interpolan retornos a frecuencia mensual.

Para describir concentración se mantienen las betas de la muestra completa:

```text
y_t = retorno_t − RF_t
a_t = y_t − sum(beta_global_j × factor_jt)
contribución_del_episodio = sum(a_t del episodio) / 36
sum(contribuciones) = alfa trimestral global = 0,59609%
```

Esto es una atribución aritmética **in-sample**, no alfa local, retorno compuesto
ni predicción fuera de muestra. Conserva también la contribución de cada factor
y el residuo por trimestre. Las participaciones sobre una suma neta pueden ser
negativas o superiores al 100%.

| Episodio | n | Retorno real compuesto | Contribución al alfa trimestral global (pp) | Alfa anualizado al excluir el episodio |
|---|---:|---:|---:|---:|
| 2018 | 4 | −6,71% | +0,01662 | +2,50% |
| 2020 | 4 | +19,05% | +0,04176 | +2,92% |
| 2022 | 4 | −9,23% | +0,13316 | +1,09% |
| 2023–2024 | 8 | +44,88% | −0,14567 | +4,99% |
| Resto de trimestres | 16 | +199,67%* | +0,55022 | — |
| Total | 36 | — | **+0,59609** | **+2,41%** sin excluir nada |

*El producto de retornos del resto abarca fechas no consecutivas; no es una
cartera invertible que hubiera identificado esos trimestres de antemano.*

La última columna reestima todos los coeficientes por OLS en las observaciones
restantes. **No publica SE ni t-stat HAC**: eliminar episodios crea huecos y no
se deben tratar trimestres separados como vecinos. La atribución con betas fijas
y la exclusión con betas reestimadas responden a preguntas distintas.

El rally 2023–2024 tiene retorno bruto positivo, pero contribución ajustada
negativa. El resultado agregado no viene de ese episodio. La subida de tipos
de 2022 contribuye positivamente al ajuste aunque el retorno bruto sea negativo.

Para no ocultar la concentración dentro de «Resto», se conserva también el
desglose completo por año de inicio del trimestre:

| Año | n | Contribución al alfa trimestral global (pp) |
|---|---:|---:|
| 2016 parcial | 2 | −0,04067 |
| 2017 | 4 | −0,00569 |
| 2018 | 4 | +0,01662 |
| 2019 | 4 | +0,18246 |
| 2020 | 4 | +0,04176 |
| 2021 | 4 | +0,30195 |
| 2022 | 4 | +0,13316 |
| 2023 | 4 | −0,04513 |
| 2024 | 4 | −0,10054 |
| 2025 parcial | 2 | +0,11217 |

**2021 representa aproximadamente el 50,7% de la suma ajustada neta y 2019
otro 30,6%**, manteniendo las betas globales. La concentración es descriptiva;
no demuestra que ese alfa sea repetible ni que proceda de un único régimen causal.

## Artefactos, interfaz y reproducción

- [inputs.csv](inputs.csv): copia íntegra de los inputs auditados anteriormente.
- [audit.json](audit.json): ajustes completos, episodios, exclusiones, atribución
  anual/trimestral, metodología, limitaciones y hashes portables LF/CRLF.
- [coefficients.csv](coefficients.csv): alfa y seis betas, SE, t, intervalos,
  fechas, tamaño y retardos de cada ajuste continuo (378 filas).
- [attribution.csv](attribution.csv): factores y residuo de cada trimestre.

Desde la raíz, sin red y sin reconstruir el backtest:

```powershell
.venv/Scripts/python.exe -m gabi.factor_stability
```

El comando admite `--inputs` y `--output`. No registra resultados como validación
ni modifica la base de experimentos. `load_audit()` comprueba las huellas de los
tres CSV antes de presentarlos.

Research Lab muestra el informe guardado con selector de coeficiente y ventana,
gráfico interactivo de estimaciones e intervalos y descargas CSV/JSON. Ranking
histórico ofrece el mismo diagnóstico para el backtest trimestral actual. Este
último exige todos los meses de factores y RF: no imputa meses ausentes, no pone
RF a cero y rechaza frecuencias distintas de tres meses o huecos.

## Alcance pendiente

No se recuperaron las 500 cestas originales de la prueba de permutación ni los
vectores completos de las tres perturbaciones de pesos históricas. **Esta
entrega no acredita estabilidad por régimen de esas dos pruebas.** La matriz
de 24 ensayos de PBO/DSR tampoco sustituye aquellas perturbaciones de pesos.
Crear otras variantes ahora sería investigación nueva, no reproducir la prueba
original. Para repetirlas fielmente hacen falta pesos completos, semillas,
cestas y retornos por periodo, con la misma muestra point-in-time.

Tampoco se estima turnover por régimen ni se atribuye causalidad al 63% agregado.
Persisten las limitaciones de identidad y universo muestreado del recálculo V1,
la alineación mensual aproximada y la escasa potencia con 36 observaciones.

## Verificación

Los tests comprueban la reproducción de la regresión HAC congelada, recuperación
de un cambio sintético de alfa/beta entre mitades, ajustes móviles contra OLS
directo, ausencia de información futura en ventanas anteriores, conciliación
exacta de atribuciones y cobertura sin duplicados, y exclusión sin HAC sobre
huecos. También cubren meses/RF ausentes, fechas inválidas, valores no finitos,
frecuencias incorrectas, diseños singulares, muestras cortas y alteración de
artefactos. El informe conserva resultados completos para inspección independiente.

Verificación de esta entrega: **526 tests correctos**, incluidos 18 de
estabilidad temporal; Ruff y mypy (42 archivos) correctos. Los ocho avisos
de pytest son los tests preexistentes de correlaciones constantes de Factor Lab.
La vista compartida se ejecutó con Streamlit AppTest, incluida la selección
de otro coeficiente y otra ventana, sin excepciones.
