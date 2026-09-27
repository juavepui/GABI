# STAT-6 (#49): preregistro de controles nulos

Sellado antes de ejecutar las simulaciones del #49. Especificación exacta en
[preregistro.json](preregistro.json), SHA-256
`2fd302ec4004550ec4080c46e8e7f0fd319ce6e3bb9c0f688134c2cae8ba29fa`.

## Estrategia y datos

Composite vigente, Top-20 equiponderado, 57 trimestres de #40 (2011-07 a
2025-07), retorno bruto sin costes. Solo se seleccionan empresas elegibles
con retorno observado. El universo y las señales son los mismos rankings
acreditados y retornos futuros de #40. Semilla fija `490047`.

## Nulos fijados

Se generan **2.048 trayectorias completas por nulo**:

1. Ranking aleatorio dentro de cada trimestre y Top-20 resultante.
2. Top-20 uniforme sin reemplazo dentro del mismo universo y trimestre.
   Es equivalente en distribución al anterior; usa sorteos independientes.
3. Top-20 aleatorio que conserva exactamente los conteos sectoriales del
   Top-20 real cada trimestre. Si falta sector, se usa `unknown`.
4. Permutación de retornos entre empresas del mismo sector y trimestre,
   manteniendo la selección real. Es **diagnóstica**: no conserva la
   autocorrelación de cada empresa.

Los tres primeros son pruebas de aleatorización condicional a los retornos
observados y a los shocks de cada trimestre; el tercero también condiciona la
composición sectorial. No se extrapolan sus p a una prueba prospectiva.
El sector histórico está ausente en estos rankings, así que el tercero
degenera al segundo y se reportará expresamente; no se inventará una
neutralidad sectorial.

## Perturbaciones y métricas

- Retraso fijo de un rebalanceo: se usa el ranking anterior para el trimestre
  actual; 56 periodos comparables, sin mirar al futuro.
- 256 vectores de pesos predefinidos por semilla: cada bloque se perturba
  como máximo 2,5 puntos porcentuales, los deltas suman cero. No se elige
  ningún vector ganador.
- Inversión de signo: Bottom-20, una sola comprobación de cordura.

Por trayectoria se calculan CAGR geométrico, Sharpe trimestral anualizado,
drawdown de NAV trimestral, ES5 de retornos trimestrales, exceso medio
trimestral frente al universo y número de las tres ventanas fijas con exceso
positivo. Para cada nulo y métrica se publican **las 2.048 observaciones**,
media, percentiles 5/50/95 y `p=(1+# simulaciones >= observado)/2049` en
dirección favorable. Son seis lecturas simultáneas; no se escogerá el mejor
percentil para declarar éxito ni para cambiar pesos.

Se reutilizarán `stats_rigor.pbo_cscv` (6 bloques) y
`stats_rigor.deflated_sharpe_ratio` para la familia fija de 257 pesos. Esto
solo diagnostica esa familia local, no reconstruye la búsqueda histórica
completa. Los resultados retrospectivos no seleccionan una variante para
Investor.
