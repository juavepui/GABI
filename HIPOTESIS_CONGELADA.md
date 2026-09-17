# Hipótesis congelada — 2026-09-17

Este documento existe por una razón concreta: toda la exploración de backtesting hecha
hasta esta fecha (ver `README.md`, secciones de backtesting) se hizo mirando los mismos
datos históricos una y otra vez — 10+ configuraciones distintas comparadas sobre el mismo
rango 2016-2025 (top-10/20/30, filtro de tendencia, sensibilidad a costes, factores
individuales vs multifactor). Eso es *data snooping* por diseño: cualquier conclusión
sacada así está contaminada por cuántas veces se ha mirado el mismo dato, y no hay forma
de corregirlo estadísticamente a posteriori con garantías.

La única salida honesta es dejar de mirar hacia atrás y **declarar la configuración que
se cree buena, por escrito, con fecha, antes de tener ningún dato nuevo con el que
verificarla**. Eso es lo que hace este archivo.

## Corte de datos (data cutoff)

**Todo dato de precio o fundamental fechado el 2026-09-17 o antes se considera "visto"** —
se usó, directa o indirectamente, para llegar a la configuración de abajo, y no puede
usarse para validarla sin dar por buena la contaminación por *data snooping* del punto 3
y 5 del checklist de sesgos de backtesting.

**Solo cuenta como validación honesta cualquier resultado calculado con datos posteriores
al 2026-09-17** — es decir, lo que pase de verdad a partir de aquí, en tiempo real, sin
volver a mirar ni ajustar nada mientras tanto.

## La hipótesis exacta

Configuración congelada, tal cual se ejecutaría hoy desde 🕰️ Ranking histórico / 📊 Screener:

- **Score**: Composite (multifactor), pesos actuales de ⚙️ Configuración:
  `Value 30% · Quality 35% · Momentum 25% · Risk 10%`
- **Nº de posiciones**: 20 (no 10) — el experimento de posiciones mostró mejor Sharpe,
  Sortino y máximo drawdown a la vez con 20 frente a 10 o 30.
- **Rebalanceo**: trimestral.
- **Universo**: S&P 500, muestreo aleatorio con semilla fija si se limita el tamaño
  (nunca alfabético — ver corrección de ese bug en el README).
- **Sin filtro de tendencia (SMA200)**: se probó y no redujo el drawdown real (reacciona
  tarde para caídas rápidas tipo COVID) — no forma parte de la hipótesis.
- **Coste asumido**: la ventaja observada en el pasado se estrechaba mucho entre 25 y
  50 puntos básicos de coste por lado — la hipótesis solo se considera confirmada si
  sobrevive a un coste realista, no solo a los 10pb optimistas usados en la mayoría de
  las comparaciones.

## La predicción concreta (para poder fallar, no solo para poder tener razón)

Durante el próximo año natural de rebalanceos trimestrales reales (2026-Q4 a 2027-Q3,
cuatro periodos), con esta configuración exacta:

1. El Sharpe ratio de la cesta de 20 posiciones será **superior** al del SPY en el mismo
   periodo — pero de forma modesta, no espectacular (algo como +0.1 a +0.3 de diferencia,
   no +0.5 o más; un salto mayor sería motivo de sospecha, no de celebración, según el
   propio chequeo de "sospechosamente bueno" que ya hicimos).
2. El máximo drawdown de la cesta **no** será mejor que el del SPY en una caída
   generalizada del mercado, si la hay — la concentración en pocas posiciones no protege
   de eso, ya lo vimos con el COVID.
3. En al menos uno de los cuatro trimestres, la cesta **perderá** claramente frente al
   SPY — si gana los cuatro, es más señal de suerte con un tema de mercado concreto que
   de ventaja estructural.

Si estas tres cosas no se cumplen, la hipótesis se da por refutada para esta
configuración concreta, no se re-interpreta a posteriori para que "sí funcionó en el
fondo".

## Punto de partida real y trazable

Ranking guardado el 2026-09-17 en 📊 Screener con esta configuración exacta (N=20,
pesos actuales), nombrado **"Hipótesis congelada 2026-09-17"** — es el primer dato real
de esta validación, no una simulación.

## Evidencia de diagnóstico (2026-09-17, no cambia la hipótesis)

Tras congelar la hipótesis de arriba, se corrieron cuatro pruebas de diagnóstico sobre
esa misma configuración (top-20, mismo rango 2016-07 a 2025-04) — no para buscar una
configuración mejor, sino para evaluar si la ya congelada tiene una base sólida o es
puro ruido con suerte. No alteran nada de lo de arriba.

- **Test de permutación (500 cestas aleatorias de 20 empresas del mismo pool elegible,
  por trimestre)**: el resultado real (+362.8% acumulado, Sharpe 0.76) queda en el
  **percentil 99.8%** de la distribución aleatoria (mediana aleatoria +195.9%, Sharpe
  0.42; percentil 95 aleatorio +280.9%, Sharpe 0.61) — de 500 cestas al azar, solo 1
  lo habría igualado o superado. Es la evidencia más fuerte de toda la sesión de que
  hay señal real, no solo azar.
- **Concentración sectorial** (media de 36 trimestres): ningún sector supera el 17.5%
  (Industrials 17.5%, Tecnología 14.6%, Consumo discrecional 11.4%, Salud 10.6%,
  Financieras 10.4%, resto <7% cada uno) — sin el patrón de 30-50% en uno o dos
  sectores que sería una señal de alarma. Es la media histórica, no garantiza que una
  foto puntual de un trimestre concreto no pueda concentrarse más por casualidad.
- **Turnover**: 63.1% de media entre rebalanceos consecutivos (mediana 65%, rango
  30-85%) — unas 12-13 de las 20 posiciones cambian cada trimestre. Confirma que el
  punto débil real es el coste de tanta rotación, coherente con el hallazgo de que la
  ventaja se estrecha mucho entre 25 y 50 puntos básicos de coste.
- **Fragilidad a los pesos**: con tres perturbaciones de pesos razonablemente distintas
  a la actual (ej. Value 45% en vez de 30%, Momentum 40% en vez de 25%, Quality 20% en
  vez de 35%), entre el 69% y el 75% de las 20 empresas se mantienen — no es el "cambian
  8 de 10" que indicaría sobreajuste a una combinación de pesos muy concreta.

**Lectura conjunta**: hay señal estadísticamente real y razonablemente robusta a los
pesos, sin concentración sectorial peligrosa de media — pero con una rotación alta que
hace que los costes reales sean el factor que más puede decidir si esto funciona en la
práctica, no solo en el papel. Nada de esto cambia la predicción congelada de arriba;
solo explica por qué se consideró razonable congelarla así.

## Cuándo revisar esto

No antes de **2027-09-17** (un año natural), o antes de acumular 4 rebalanceos
trimestrales reales completos desde hoy, lo que llegue después. Revisarlo antes,
aunque sea "solo para mirar cómo va", vuelve a contaminar la validez de la prueba —
mirar a medio camino y decidir parar o cambiar algo en función de lo que se ve es
exactamente el mismo error que estamos intentando evitar.

## Addendum 2026-09-17 (mismo día): dos bugs de medición corregidos — no es reabrir la hipótesis

Una revisión externa adicional del código (no de la configuración, del *motor de
medida*) encontró dos fallos reales en `src/gabi/multifactor_backtest.py` y
`src/gabi/edgar.py`, ya corregidos con tests:

1. **Anualización con recuento de periodos, no con años de calendario reales**:
   `_risk_metrics()` calculaba `years = n_periodos_validos / periodos_por_año`. Si algún
   trimestre se saltaba (`skipped`), el mismo retorno total se comprimía en menos años de
   los que realmente pasaron, inflando el anualizado y el Sharpe. Corregido: ahora se pasa
   el número de años real (fecha de fin del último periodo menos fecha de inicio del
   primero). **No afecta a las cifras ya congeladas arriba**: la validación 2016-07 a
   2025-04 no tuvo ningún trimestre saltado (36/36 válidos), así que el bug no llegó a
   dispararse en ese cálculo concreto — pero sí lo haría en cuanto apareciera un hueco,
   incluida la validación prospectiva que empieza ahora.
2. **El guard de reciclaje de ticker no era point-in-time correcto**: `get_last_filed_dates()`
   miraba el filing SEC más reciente **de cualquier fecha**, incluido el futuro respecto al
   periodo evaluado. Si un ticker se recicla y la empresa nueva presenta filings bajo el
   mismo símbolo, esos filings futuros podían colarse como "reciente" y el guard nunca
   saltaba — justo el fallo que debía detectar. Corregido con un parámetro `as_of`: solo
   cuentan los filings con `filed_date <= fecha_evaluada`. Verificado con un test que
   reproduce el caso exacto (filing viejo de 2018 + filing futuro de 2026 simulando la
   empresa recicladora — el guard ahora sí salta).

**Por qué esto no es "descongelar por antojo"**: corregir cómo se mide algo no es lo mismo
que buscar una configuración distinta porque el número no gustaba — es arreglar la
herramienta con la que se leerá el resultado real que ya está en marcha. La configuración
congelada (Composite, N=20, trimestral, sin filtro de tendencia) y la predicción concreta
de la sección de arriba **no cambian**.

## Contraste con factores académicos (Kenneth French Data Library) — 2026-09-17

Nuevo módulo `src/gabi/academic_factors.py`: descarga y cachea las series mensuales de
Fama-French 5 factores + Momentum (Mkt-RF, SMB, HML, RMW, CMA, Mom — gratis, sin API key,
mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html) y regresiona el retorno
de la estrategia contra ellos: `retorno_GABI − RF = alfa + Σ(beta_i · factor_i) + error`.
Disponible también en 🕰️ Ranking histórico tras ejecutar el backtest multifactor.

**Resultado real sobre los 36 trimestres de la validación (2016-07 a 2025-04, top-20):**

| | Valor |
|---|---|
| R² | 0.915 |
| Alfa (por trimestre) | +0.95% (t-stat +1.61) |
| Alfa anualizado | **+3.85%** |
| Beta Mercado (Mkt-RF) | +0.974 (t-stat +12.68) |
| Beta Tamaño (SMB) | +0.240 (t-stat +1.68) |
| Beta Value (HML) | +0.155 (t-stat +1.46) |
| Beta Calidad (RMW) | +0.264 (t-stat +1.80) |
| Beta Inversión (CMA) | +0.006 (t-stat +0.04) |
| Beta Momentum (Mom) | +0.023 (t-stat +0.22) |

**Lectura honesta**: el 91.5% de la varianza del retorno de la estrategia ya la explican
los 6 factores académicos conocidos — mayormente exposición al mercado (beta≈1, como
cualquier cartera de acciones long-only) con tilts moderados a tamaño y calidad/rentabilidad
(coherente con que Quality es el bloque con más peso, 35%, en el Composite). El alfa
apunta positivo (+3.85% anualizado, lo que GABI aportaría por encima de esas exposiciones
ya conocidas) pero **su t-stat (1.61) no llega ni al umbral convencional de 2.0, y mucho
menos al 3.0 que proponen Harvey, Liu y Zhu para corregir por las muchas configuraciones
que se prueban en este tipo de investigación** — no se puede afirmar con confianza
estadística que ese alfa sea distinto de cero. Curioso además: pese a que Momentum pesa un
25% en el Composite, la beta de Momentum realizada es prácticamente nula (0.023) — la
construcción de GABI (concentrada, con límites de sector/cobertura) no se traduce en la
misma exposición que el factor académico de momentum (long-short, universo completo).

Esto no cambia la hipótesis congelada — es evidencia adicional, en la misma línea que el
resto del diagnóstico: hay una señal direccional real, pero modesta y no demostrada con
la confianza estadística que haría falta para actuar sobre ella sin más validación.
