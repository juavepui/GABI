# STAT-7 (#50): incertidumbre mediante bloques temporales

Especificación fijada el 2026-09-28 antes de ejecutar el análisis de #50.
No se buscan pesos, variantes ni la longitud de bloque que favorezca a GABI.
Es una descripción retrospectiva de incertidumbre, no evidencia OOS nueva.

## Método y sensibilidad fijados

Bootstrap circular con bloques de longitud fija, conservando el orden dentro
del bloque y envolviendo al principio al llegar al final. Se extraen los
mismos índices para estrategia y todos sus benchmarks: no se remuestrean
independientemente. Cada réplica conserva el número de observaciones.
Se ejecutan **4.096 réplicas**, semilla **500050**, percentiles 2,5/50/97,5.

Longitud principal: **20 sesiones** para retornos diarios (aproximadamente
un mes), **4 trimestres** para series trimestrales (un año). Sensibilidades
fijas: 10/40 sesiones y 2/8 trimestres. La elección usa horizontes económicos,
no retornos observados; no se afirma que sea óptima. Se presentan las tres
longitudes, sin seleccionar un ganador. Para otros experimentos de Research
Lab: 3 meses (sensibilidad 2/6), 2 semestres (sensibilidad 4), o 2 años
(sensibilidad 4). No se usa remuestreo IID en el producto.

Los bloques preservan dependencia local, pero las uniones de bloques la
rompen. La inferencia presupone dependencia débil y estacionariedad
aproximada: cambios de régimen o colas no observadas no quedan resueltos.
El drawdown y ES son especialmente sensibles al histórico y al método;
sus intervalos son rangos percentiles descriptivos del remuestreo, sin
garantía de cobertura nominal del 95 %.

## Datos congelados por contenido

Sin descargar datos ni reconstruir rankings:

1. V2 Top-20 neto frente a SPY: NAV diario guardado en
   `docs/historical-revalidation-2011-2025/acreditado-38-continua/v2-top20-nav.csv`.
   Se calcula `pct_change(fill_method=None)` antes de restringir al tramo
   invertido, desde la primera fecha de `v2-top20-periods.csv`; así se
   conserva el retorno de la primera sesión y sus costes.
2. V1 Top-20 neto frente a SPY y universo elegible: retornos trimestrales de
   `acreditado-38-continua/v1-top20-periods.csv` (`retorno`, `spy`, `universo_ew`).
   Las ventanas deben ser consecutivas y de frecuencia trimestral.
3. IC y spread Q5−Q1 por trimestre de #40, de
   `docs/cross-section-test/por-trimestre.csv`. Se remuestrean las medias
   temporales ya agregadas, no empresas como observaciones independientes.

SHA-256 de cada entrada, configuración y código; seed, frecuencia,
fechas, número de observaciones y entorno se guardan en el resultado.
No se eliminan/imputan NaN, huecos, duplicados ni desalineaciones entre
series. Se exigen al menos 30 observaciones y bloques de 2 a n/2.

## Métricas y convención

- CAGR geométrico; volatilidad muestral y Sharpe anualizados por la frecuencia
  declarada (252/4 en los artefactos), tipo libre de riesgo anual = 0.
- Drawdown máximo negativo, incluyendo NAV inicial 1. El drawdown trimestral
  no representa caídas intratrimestrales.
- ES5 de pérdidas `−retorno`, con masa fraccionaria en la frontera, como
  `portfolio_metrics.historical_tail_risk`. Horizonte de una observación;
  no se anualiza. Se declara la masa de cola y su escasa resolución.
- Exceso medio por observación, diferencia de CAGR y diferencia de Sharpe,
  siempre sobre trayectorias emparejadas.
- Fracciones de réplicas con exceso medio > 0, CAGR superior, Sharpe superior
  y drawdown ≤ −20 %. Son frecuencias bootstrap condicionadas al histórico,
  no p-valores, probabilidades posteriores ni probabilidades de éxito futuro.

Sharpe no estimable (volatilidad nula) se conserva como ausente, informando
cuántas réplicas permiten estimarlo; no se descarta la trayectoria entera.
Pérdida total (−100 %) se admite; retornos por debajo de −100 % se rechazan.
El estimador observado se distingue de la media y mediana bootstrap.

## Contraste e integración

Para exceso medio, IC y spread: intervalo de la media HAC/Newey-West
existente, con sus retardos automáticos y aproximación normal, junto al
intervalo percentil de bloques. Se informa si difieren al excluir cero;
no se considera superior un método porque favorezca la hipótesis.
No se corrige por selección retrospectiva ni se hacen tests confirmatorios
con estas comparaciones múltiples.

Research Lab mostrará el artefacto guardado y permitirá calcular el mismo
diagnóstico con series de experimentos compatibles, sin frecuencia implícita
ni unir huecos. Habrá tablas de intervalos/sensibilidad, histogramas,
fracciones bootstrap y exportación de parámetros y distribuciones completas.

## Referencias

- [arch: bootstrap temporal circular](https://bashtage.github.io/arch/bootstrap/timeseries-bootstraps.html).
- [Nordman y Lahiri (2014): selección de bloques](https://arxiv.org/abs/1403.3275).
  La longitud afecta a la precisión; nuestros horizontes son decisiones
  prácticas preregistradas, no estimadores óptimos derivados de ese artículo.
