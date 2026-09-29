# RCF v1: recompras y generación de caja

Prueba exploratoria retrospectiva, un candidato, 2026-09-29. Se publica motor, protocolo y preregistro antes del primer cálculo de puntuaciones/rentabilidad RCF. El historial 2011–2025 ya se ha observado: esta publicación no crea una prueba independiente. Objetivo #60 pendiente.

## Hipótesis económica y alcance

Una empresa que convierte más caja operativa en FCF y dedica una fracción mayor de ese FCF a recompras comunes podría ofrecer mejores retornos que SPY. Es una hipótesis nueva de asignación de caja, sin ventaja asumida. La [investigación de Boudoukh, Michaely, Richardson y Roberts](https://www.nber.org/papers/w10651) estudia medidas de payout que incluyen recompras: **RCF no replica su payout yield**, porque aquí no se acreditan dividendos/emisiones completos ni capitalización consolidada para todas las clases.

Se utilizan exclusivamente inputs anuales de la [auditoría v2](../capital-inputs/v2/README.md), con sus fuentes admitidas, cuarentena, último filing y reglas temporales. [Company Facts](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) cubre conceptos estándar aplicados al emisor completo; la ausencia de un tag no equivale a cero. No se reconstruyen emisiones, opciones o dilución ni se incorporan nuevas fuentes para este candidato.

Se fija una sola clase por CIK, ticker alfabéticamente primero dentro del universo fechado original, **antes** de aplicar requisitos o consultar retornos; ninguna sustitución retrospectiva. Se excluye la división SIC H (finanzas, seguros e inmobiliarias): su inversión/financiación no tiene una interpretación homogénea con OCF menos compras de PP&E. No se modifica el universo original ni se afirma que sea el S&P 500 completo.

Elegibilidad: último filing anual vigente y admitido; recompras comunes brutas, OCF total y compras de PP&E reportados, finitos y del mismo accession e inicio/fin anual; capex y recompras no negativos; OCF > 0; FCF = OCF − capex > 0; 0 < recompras ≤ FCF. Todas estas reglas se fijan antes de ver la cobertura del nuevo subconjunto y sus retornos. Sin imputación, sin rescate de filings anteriores.

El filtro significa que las recompras no exceden esa medida de caja anual. **No prueba** que se financiaran sin deuda, que las acciones netas disminuyeran o que quedase caja después de dividendos, adquisiciones y otros usos. Se conserva el sesgo posible por emisores desaparecidos, tags estándar y fuentes excluidas. Los datos faltantes y el filtro económico condicionan la población.

## Puntuación y cartera

Dos cocientes adimensionales: recompras brutas / FCF positivo y FCF / OCF positivo, ambos con mayor valor orientado a mayor puntuación. Se evita mezclar flujos del emisor con capitalización de una clase y no se requieren datos de splits. No son yields de valoración. Percentiles por división SIC en emisores elegibles únicos, mínimo ocho observaciones por división; fallback global entre elegibles y empates con rango medio. Score RCF = media de los dos percentiles, pesos 50/50.

Hasta 20 posiciones equiponderadas, máximo seis por división, desempate por score descendente y ticker ascendente. Cada slot recibe 5 % del capital; slots vacíos quedan en efectivo sin interés. Un retorno seleccionado ausente/no finito o inferior a −100 % invalida el periodo; no se elimina la empresa ni se redistribuye su peso. IC Spearman entre score y retorno entre emisores elegibles, mínimo 30 pares y variación en ambas series; retornos inválidos se excluyen del IC, con recuentos explícitos.

Los 57 periodos independientes utilizan el calendario y retornos congelados de la primera familia. SPY ajustado en idénticas sesiones exactas. Cada periodo parte de 100.000 USD y financia compra/venta y ambas comisiones: 10 pb/lado base, 25 pb/lado estrés, 1 USD/operación; SPY paga su propio round-trip. Las comisiones de salida se reservan en efectivo. Antes de impuestos y conversión de divisas. Los huecos entre periodos y las salidas heredadas impiden inferir CAGR o riesgo diario.

Control descriptivo secundario: cartera equiponderada de todos los emisores elegibles, completamente financiada con costes de su número de posiciones. Se publica la diferencia frente a ese control para distinguir selección de pertenencia al subconjunto. No se optimiza ni se prueba otro candidato a partir de él. Si cualquier retorno del control falta, su periodo es inválido.

## Puerta fijada de auditoría diaria

Una nueva configuración, mínimo acumulado conocido **34**. El registro completo de búsquedas sigue pendiente. Se aplica un guard conservador α = 0,05/34 (IC y cola inferior), sin afirmar control global del error mientras ese registro esté incompleto. No se seleccionan retrospectivamente ventanas, costes o umbrales.

La promoción exige simultáneamente:

1. Al menos 30 emisores elegibles en al menos 30 fechas y ocho fechas en cada ventana fija 2011–15, 2016–20, 2021–25.
2. IC medio positivo, estimable en al menos 30 periodos; test unilateral HAC Bartlett con tres lags, p < 0,05/34.
3. Exceso neto medio frente a SPY positivo en cada ventana y ambos costes, mínimo ocho periodos por ventana y 30 en total.
4. Cota inferior de exceso medio positiva en ambos costes: bootstrap circular sobre el calendario completo, bloques de cuatro trimestres, 5.000 réplicas, semilla 20260929, cola 0,05/34. Índices compartidos entre costes. Una fecha ausente impide la cota, sin comprimir el calendario.

La intersección de los dos escenarios evita escoger el favorable. Pasar solo permite una auditoría diaria de cartera/identidad/dividendos/terminales/costes/riesgo; no demuestra la ventaja ni el objetivo anual de #60. Fallar archiva este diseño sin ajustar sus reglas para rescatarlo. Las reservas #43/#44 permanecen intactas y no se ofrecen como muestra independiente de RCF.

## Verificación

El preregistro sella código y protocolo, incluidos los motores padre. Se fija el resultado canónico completo de la auditoría anual, sus cinco artefactos, fuentes SEC y snapshot original. Los CSV conservan todos los emisores y motivos de exclusión, decisiones, control y comparación SPY. Se rechaza sobrescribir resultados publicados; reproducción en otra carpeta ignorada, coincidencia de JSON canónico y cinco CSV, pruebas sintéticas y suite del repositorio antes de publicar.

Comandos desde el repositorio:

```powershell
.venv/Scripts/python.exe -m gabi.repurchase_cash_strategy --preregister
.venv/Scripts/python.exe -m gabi.repurchase_cash_strategy --analyze
.venv/Scripts/python.exe -m gabi.repurchase_cash_strategy --verify
.venv/Scripts/python.exe -m gabi.repurchase_cash_strategy --reproduce data/research_reproductions/repurchase_cash_v1_20260929
```
