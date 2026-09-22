# Auditoría retrospectiva PBO/DSR — 2026-09-22

Implementación del [issue #12](https://github.com/juavepui/GABI/issues/12).
Se reconstruyeron **24 ensayos documentados**, con sus **36 retornos trimestrales
comunes**, sobre una copia consistente de la base local. La matriz completa está
en [returns.csv](returns.csv); parámetros, procedencia, resultados, sensibilidades
y exclusiones están en [audit.json](audit.json). La app los muestra en Research Lab.

El alcance es **parcial respecto al proceso histórico completo**: no se conserva
un registro exhaustivo de todos los intentos originales. Reejecutar reglas con
código/datos actuales no recupera las series que se vieron en cada sesión pasada.

## Qué se reconstruyó

Familia principal, nueve variantes con coste fijo de 10 pb por lado:

- Top-10, Top-20 y Top-30 trimestrales.
- Top-10 trimestral con exposición al 50% si SPY está bajo su SMA200 al rebalancear.
- Top-20 trimestral con bandas de permanencia 1,3×, 1,5× y 2,0×.
- Top-20 semestral y anual.

Además se conservaron quince ensayos de costes expresamente documentados:
Top-10 con 25/50/100 pb; Top-20 trimestral, sus tres bandas, semestral y anual
con 25/50 pb. Se presentan como sensibilidad, no como quince estrategias nuevas
e independientes. No se generó una cuadrícula adicional de parámetros.

Configuración común: motor V1, pesos Value/Quality/Momentum/Risk 30/35/25/10,
2016-07-02 a 2025-07-02, muestra de 200 empresas por fecha con semilla 42,
cobertura mínima individual 70% y del universo 50%. El Top-20 trimestral se
mantiene como configuración elegida antes de calcular el informe.

Fuera de la matriz, identificados en el manifiesto:

- Las tres perturbaciones de pesos de HIPOTESIS_CONGELADA: solo constan pesos
  parciales y solapamiento de posiciones; no hay vectores completos recuperados.
- Factores individuales frente al Composite: faltan especificaciones completas.
- Todos los intentos/versiones con bugs, universos o coberturas anteriores.
- V2, otras construcciones de cartera y pruebas sobre rangos diferentes.

## Resultados sobre las series reconstruidas

| Universo de ensayos | Variantes | PBO, 6 bloques | DSR del Top-20 | SR*₀ anualizado |
|---|---:|---:|---:|---:|
| Coste fijo 10 pb | 9 | **10,0%** | **94,08%** | 0,1608 |
| Incluyendo sensibilidad a costes | 24 | **10,0%** | **93,29%** | 0,1844 |

El Sharpe aritmético anualizado del Top-20 es **0,7367**. Su serie coincide,
en los 36 periodos, con la reconstrucción V1 usada en la auditoría HAC anterior.

PBO principal significa que la elección por máximo Sharpe IS quedó en o bajo
la mediana OOS en **2 de 20 particiones**. La elección histórica también miró
drawdown: este PBO no modela exactamente aquella decisión multicriterio ni es
una probabilidad posterior de que la estrategia concreta sea falsa.

El DSR principal está por debajo de 95%. **No equivale a una probabilidad del
94% de que la estrategia funcione** ni elimina los ensayos ausentes. La
correlación media entre las nueve series es 0,9551: son variantes muy próximas.
Se declara el número nominal de ensayos; no se afirma haber estimado un número
exacto de ensayos independientes.

Sensibilidad del PBO a particiones de igual tamaño, conservando las 36 fechas:

| Bloques | Combinaciones | PBO, 9 variantes | PBO, 24 variantes |
|---:|---:|---:|---:|
| 4 | 6 | 0,00% | 0,00% |
| 6 (principal) | 20 | 10,00% | 10,00% |
| 12 | 924 | 8,55% | 6,44% |

La resolución de seis bloques es modesta; las particiones tampoco son ensayos
independientes. No se eligió el número de bloques para minimizar PBO.

Sensibilidad DSR de la familia principal al número supuesto de ensayos:

| N supuesto | DSR |
|---:|---:|
| 9 observados | 94,08% |
| 12 | 93,58% |
| 24 | 92,37% |
| 50 | 91,07% |
| 100 | 89,84% |

Esta sensibilidad mantiene fija la varianza de los nueve Sharpes observados.
No reconstruye los ensayos perdidos ni determina una cota garantizada: esos
ensayos podrían modificar también la dispersión y dependencia entre variantes.

## Método y límites

Las carteras semestrales/anuales mantienen su cesta hasta su rebalanceo; se
valoran en los cierres trimestrales intermedios con precios ajustados reales.
No se dividen retornos anuales entre cuatro ni se interpolan curvas. Las marcas
compuestas reproducen el retorno terminal V1, incluidos sus costes. El capital
no invertido por SMA200 gana cero; la señal usa solo sesiones anteriores o
iguales a la fecha de rebalanceo. Esto es una reconstrucción de la regla
documentada, sin añadir un modelo nuevo de ejecución o de remuneración de caja.

Todos los estadísticos usan media aritmética de excesos sobre RF dividida por
desviación muestral, anualizada con √4. RF es la hipótesis constante del 4% anual,
convertida a trimestre; no una serie histórica de letras del Tesoro. Asimetría y
curtosis se estiman sobre la misma serie. PBO también ordena por ese Sharpe de
excesos. DSR usa N nominal y la varianza observada entre Sharpes. Son estimaciones
asintóticas; no corrigen autocorrelación temporal como HAC.

Las formulaciones se contrastaron con los artículos de los autores:
[DSR, Bailey y López de Prado](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf)
y [PBO/CSCV, Bailey et al.](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf).
Los empates IS se resuelven ponderando por igual a sus ganadores; los rangos OOS
empatan por rango medio. El criterio de fallo es logit ≤ 0. Se conservan logits,
pesos y número de particiones empatadas en el JSON.

La auditoría falla ante huecos, precios ausentes, rankings alterados o matrices
no comparables. Conserva los controles V1 de reciclaje de tickers. La identidad
histórica sigue usando el modo no estricto existente: el snapshot tiene cero
alias acreditados. Un universo muestreado y los límites de las fuentes gratuitas
siguen siendo limitaciones materiales, aunque no falte ningún trimestre.

## Por qué sustituye la lectura anterior

La auditoría antigua del experimento #10 conservaba solo la serie elegida.
Usaba N=100, ocho configuraciones, DSR≈0,83 y PBO≈0,40 sobre seis variantes
trimestrales. Su DSR partía de Sharpes basados en CAGR y mezclaba frecuencias;
no era el cálculo homogéneo de media/desviación que requiere la fórmula.
No debe interpretarse como una corrección completa del proceso de búsqueda.

El nuevo resultado usa N=200, incluye SMA200, conserva todas las series y observa
todas las carteras trimestralmente. Las diferencias numéricas mezclan estos
cambios; **no se atribuyen exclusivamente a la ampliación del número de ensayos**.

## Reproducción y registro

Recalcular únicamente PBO/DSR desde los dos artefactos publicados, sin red,
snapshot privado ni reconstrucción de rankings:

```powershell
uv run python -m gabi.overfitting_audit --analyze-only
```

Reconstruir desde la caché local completa (la primera ejecución prepara un
snapshot SQLite y un ranking por fecha; después verifica sus huellas):

```powershell
uv run python -m gabi.overfitting_audit --register
```

Si cambian los inputs/código, usar un `--cache-dir` nuevo. La matriz CSV tiene
huella SHA256 con saltos LF canónicos, para que un checkout Windows/Linux no
rompa la comprobación. El JSON conserva huellas de fuentes, snapshot, rankings,
código de auditoría y código estadístico, además del catálogo y las exclusiones.
`--register` guarda cada serie en Research Lab como RESEARCH y es idempotente
para esa misma matriz/configuración; los identificadores quedan en el JSON.

Verificación: **508 tests**, Ruff y mypy correctos; 39 módulos importados y 17
archivos de app compilados. Las pruebas cubren la equivalencia de marcas con V1,
costes de posiciones mantenidas, caja parcial, ausencia de interpolación, matriz
incompleta, empates CSCV, sensibilidad DSR, portabilidad y registro de cada serie.
