# Búsqueda de una estrategia que supere al S&P 500

Inicio: 2026-09-28, por petición explícita del propietario. El objetivo es encontrar una estrategia invertible con ventaja económica y evidencia independiente frente al S&P 500. No se considera logrado por implementar herramientas, obtener un score alto o elegir el mejor backtest.

## Criterio propuesto de éxito

Pendiente de la preferencia solicitada al propietario: **mayor rentabilidad neta con riesgo similar o menor**. Como objetivo operativo inicial se propone ≥2 puntos porcentuales de CAGR anual adicional frente a SPY con dividendos, costes y calendario comparables. La diferencia debe ser positiva también con costes estresados y tener una cota inferior simultánea del 95 % positiva en una muestra independiente. Volatilidad diaria ≤110 % de SPY y pérdida máxima no más de 5 puntos porcentuales peor; se publicará también ES. Son criterios de decisión propuestos antes de medir candidatos, no promesas, parámetros optimizados ni hechos estadísticos.

Solo posiciones largas, sin apalancamiento, con fuentes gratuitas y ejecución manual/local. Los resultados se expresarán en USD netos de costes supuestos y antes de impuestos/efectos personales de divisa. La aprobación de capital real requerirá una decisión separada del propietario después de revisar evidencia y ejecución.

## Primera familia de investigación: exactamente tres candidatos

Se fijan antes de calcular sus puntuaciones/retornos. La literatura motiva variables, no acredita estos diseños: [Quality Minus Junk](https://www.aqr.com/Insights/Research/Working-Paper/Quality-Minus-Junk), [Value and Momentum Everywhere](https://www.aqr.com/Insights/Research/Journal-Article/Value-and-Momentum-Everywhere) y [valoración por flujos de caja](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/background/valintro.htm). Son adaptaciones long-only, no reproducciones de carteras long-short académicas.

- **QV:** media equiponderada de valoración y calidad persistente. Valor: PER, P/B y EV/EBITDA positivos, al menos dos. Calidad: ROIC anual medio, margen operativo anual medio y proporción de ejercicios con FCF positivo; al menos dos, con ≥3 ejercicios en ROIC/margen y ≥3 en FCF. Cada componente es un percentil orientado.
- **QVM:** media equiponderada de valoración, calidad persistente y momentum. Momentum: retorno 12 meses, fuerza relativa 6 meses y precio/SMA200; al menos dos. Son las variables existentes de GABI, sin afirmar que sean el momentum académico 12–2.
- **QE:** media equiponderada de calidad persistente y brecha de expectativas. Brecha: CAGR histórico de FCF menos crecimiento implícito del reverse DCF ya calculado con 9 % de descuento, 2,5 % terminal y cinco años. Se exige dato válido en ambos. El crecimiento pasado es un proxy, no una previsión del futuro.

Percentiles dentro de la división SIC histórica con ≥8 observaciones válidas; con menos, fallback global indicado. Sin imputación. Universo condicionado al elegible del archivo congelado #40/#48 (Composite disponible, cobertura ≥70 %); no se presume que represente íntegramente el S&P 500. Cada modelo propone hasta 20 empresas, con máximo seis por división SIC; orden score descendente y ticker ascendente para empates. Los slots vacíos quedan en efectivo, peso fijo 1/20, interés cero. Este universo/filtro/taxonomía se declara para evitar atribuir al modelo una cobertura que los archivos no ofrecen.

## Etapa 1: diagnóstico trimestral exploratorio

Usar los 57 rankings/retornos congelados de 2011-07-02 a 2025-07-02 y las asignaciones SIC fechadas publicadas. Verificar sus huellas antes de calcular. No descargar datos ni modificar la base operativa.

- Reportar elegibilidad/cobertura y todas las selecciones por fecha/modelo.
- IC Spearman por trimestre con ≥30 pares; fechas sin IC mantienen su posición en el calendario. Media con HAC Bartlett fijo de tres retardos, ≥30 trimestres, unilateral; Holm de exactamente tres IC.
- Retorno de hasta 20 slots frente al SPY en **las mismas fechas exactas de entrada/salida**. Ausencias de retorno seleccionado invalidan el periodo; no se elimina la empresa ni se sustituye por retorno cero.
- Costes: round-trip completo de cada periodo independiente, 10 pb/lado +1 USD/operación sobre 100.000 USD; estrés 25 pb/lado +1 USD. SPY soporta su propio round-trip comparable. Se conserva el cash no invertido.
- Comparar exceso neto medio y ventanas fijas 2011–15/2016–20/2021–25. Para la familia, cotas inferiores bootstrap circular de bloques trimestrales de tamaño cuatro, 5.000 réplicas, semilla 20260928 y Bonferroni unilateral 0,05/3. No bootstrap de empresas como si fueran fechas independientes.

**Esta etapa no es un backtest continuo de cartera.** Los retornos heredados tienen ventanas que pueden dejar huecos entre trimestres; no se unen ni se annualizan como CAGR. Son periodos de inversión independientes, sin reutilizar un NAV compuesto. No se estima drawdown diario a partir de cuatro puntos al año. La fuente heredada puede salir por evento terminal o último precio disponible; esta política debe auditarse antes de cualquier certificación de inversión.

Un candidato con IC positivo tras Holm, exceso neto medio positivo en todas las ventanas y cota inferior familiar positiva en ambos escenarios de costes puede **pasar a auditoría diaria**, si hay al menos 30 periodos válidos y ninguna ventana con menos de ocho. La falta de cobertura se publica; no se cambian umbrales o fórmulas para conseguir aprobación. Los tres candidatos y todos los fallos se conservan. Cualquier diseño posterior es una familia/version nueva, contabilizada aparte.

## Etapas siguientes y reserva de evidencia

1. Para un candidato prometedor: cartera diaria financiada, identidad/precios acreditados, dividendos, terminales, costes de rebalanceo/entrada/salida, concentración, turnover, exposición a factores y análisis de incertidumbre emparejado. Comparar CAGR neto, volatilidad, drawdown y ES con SPY. No se autoriza promoción por IC exclusivamente.
2. Congelar un modelo único antes de abrir una muestra independiente adecuada y/o iniciar un registro prospectivo nuevo. Horizonte, potencia, revisiones y corrección por búsqueda deben fijarse antes de observar resultados. Las fuentes gratuitas y la muestra temporal disponible pueden limitar la potencia; no se promete una demostración rápida.
3. Exigir los criterios económicos/estadísticos acordados en esa evaluación. Con resultado adverso o insuficiente, la estrategia permanece no demostrada y no sustituye al benchmark.

2011–2025 ha sido observado en estudios anteriores: ninguna partición retrospectiva, walk-forward o nuevo bootstrap lo vuelve una muestra intacta. La advertencia sobre selección por backtests está desarrollada por los autores de [The Probability of Backtest Overfitting](https://escholarship.org/uc/item/4w1110bb).

Las pruebas ciegas #43 (GABI/Value) y #44 (GABI sin cambios fuera del S&P 500) conservan modelos, fechas y reservas originales. No se abren, reparten, renombran ni convierten sus datos en validación del nuevo diseño. El seguimiento nuevo necesita un registro separado. La primera familia suma tres configuraciones al recuento, cuyo historial previo documentado contiene al menos 30; el total acumulado debe reconciliarse antes de una prueba confirmatoria.
