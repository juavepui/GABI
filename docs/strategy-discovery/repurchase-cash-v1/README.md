# RCF v1: resultado de recompras y generación de caja

**Objetivo pendiente. Este candidato falla la puerta fijada y no pasa a auditoría diaria.** RCF pierde frente a SPY después de costes en el promedio del historial y en dos de las tres ventanas. No se cambia Investor ni se propone invertir con este modelo.

Seguimiento: [issue #60](https://github.com/juavepui/GABI/issues/60). Motor, [protocolo](PROTOCOLO.md), [preregistro](preregistro.json) y pruebas publicados **antes del primer cálculo real** en `f922cb377a48b66f6032262ee5257ace7d33af62`. Se añade exactamente una configuración: mínimo conocido acumulado 34; registro completo aún pendiente. El historial ya se había observado y sigue siendo exploratorio.

## Qué se probó

Una sola hipótesis: mayor conversión de caja operativa en FCF y mayor fracción de ese FCF destinada a recompras comunes podrían mejorar el rendimiento. Score = media equiponderada de percentiles de FCF/OCF y recompras brutas/FCF, por división SIC histórica o fallback global declarado.

Último filing anual admitido y vigente, tres componentes reportados con igual accession e inicio/fin del ejercicio, OCF y FCF positivos, recompras positivas y no superiores al FCF. Se excluye SIC H y se fija una clase alfabética por CIK antes de puntuar o consultar retornos. No se imputan ausencias, no se suman opciones/emisiones, no se usan acciones brutas como dilución ni capitalización de una clase para normalizar flujos del emisor. Estos cocientes no son un shareholder/payout yield.

Se heredan los 57 periodos independientes originales, aproximadamente trimestrales, y SPY ajustado en idénticas sesiones exactas. Top-20, máximo seis por división, pesos de 5 %, slots vacíos en efectivo. En este ensayo se seleccionan 20 posiciones en todas las fechas, sin retornos elegidos ausentes. Cada periodo parte de 100.000 USD y financia compra/venta y comisiones sin deuda; SPY financia su propio round-trip. Antes de impuestos y FX.

## Resultado frente a SPY

**Puntos porcentuales de exceso neto medio por periodo, no CAGR ni rentabilidad anualizada.** Los huecos entre periodos impiden convertir estas cifras en una cartera continua. No se estima riesgo diario porque el candidato no supera la puerta preliminar.

| Costes | Periodos válidos | Exceso neto medio | Cota inferior con guard de búsquedas |
|---|---:|---:|---:|
| Base: 10 pb/lado + 1 USD/operación | 57 | −0,358 pp | −1,747 pp |
| Estrés: 25 pb/lado + 1 USD/operación | 57 | −0,357 pp | −1,742 pp |

Cota de media mediante bootstrap circular del calendario completo: bloques de cuatro trimestres, 5.000 réplicas, semilla 20260929, cola unilateral 0,05/34. Se comparten índices entre costes y una fecha ausente impediría la cota. El guard contempla el mínimo de configuraciones conocido; **no demuestra control global del error** con un registro previo incompleto.

| Ventana fija | Periodos | Exceso base | Exceso estrés |
|---|---:|---:|---:|
| 2011–15 | 18 | −0,154 pp | −0,153 pp |
| 2016–20 | 20 | +0,192 pp | +0,192 pp |
| 2021–25 | 19 | −1,132 pp | −1,128 pp |

IC Spearman medio 0,01318 en 57 fechas; error estándar HAC 0,01263, p unilateral **0,1505**. El p con guard de 34 búsquedas es 1,000. Falla incluso sin corrección; no hay señal de ordenación estadísticamente defendible con este ensayo. La puerta exigía p < 0,05/34, exceso positivo en las tres ventanas y cota inferior positiva con ambos costes.

Control descriptivo secundario: RCF supera en promedio al conjunto equiponderado de emisores elegibles en solo **0,063 pp por periodo** (base; estrés 0,062 pp), sin prueba adicional de significación. Ese control utiliza todos los elegibles, comisiones por cada posición y los mismos costes por lado; sus 57 periodos son válidos. La selección no convierte el subconjunto en una cartera superior al índice. No se escoge retrospectivamente otra combinación a partir del control.

## Cobertura y exclusiones

18.289 símbolo-fechas, 18.242 emisor-fechas originales; 5.010 emisor-fechas elegibles (**27,46 %** del universo condicionado). Entre 57 y 116 emisores elegibles por fecha: el tamaño de muestra supera la puerta en las 57 fechas (18/20/19 por ventana). Esto no elimina el sesgo de fuentes o selección. Los 671 emisor-fechas elegibles en divisiones con menos de ocho observaciones usan el fallback global en ambos cocientes.

Motivo de exclusión principal, con prioridad fijada en el motor; los recuentos corresponden a símbolo-fechas y no representan defectos necesariamente independientes:

| Motivo | Registros |
|---|---:|
| Elegible | 5.010 |
| Componente ausente o no admitido por las reglas | 8.361 |
| División financiera H | 2.951 |
| Recompras superiores al FCF | 1.107 |
| Recompras reportadas iguales a cero | 400 |
| Generación de caja no positiva | 304 |
| Filing en cuarentena de fuente | 88 |
| Clase adicional del mismo CIK | 47 |
| Sin filing anual vigente | 21 |

No aparece un desajuste adicional de inicio/fin entre los tres componentes admitidos en este subconjunto. Los tres flujos pertenecen al emisor completo. La medida FCF utilizada es OCF menos compras de PP&E y omite otros usos de inversión/caja. Recompras ≤ FCF no acredita ausencia de financiación externa ni reducción neta de acciones: faltan dividendos, otras inversiones y emisiones completas. La cuarentena y los tags estándar pueden excluir emisores de forma no aleatoria, incluidos desaparecidos. La clase alfabética tampoco está acreditada como la más líquida.

## Artefactos y decisión

Resultado canónico: `207a1011e843cb31bf1c08a95330c69bccf1f6353ad22ba154aa27e0ebd00462`.

- [resultado.json](resultado.json): fuentes selladas, versiones, todos los fallos y limitaciones.
- [scores.csv](scores.csv): los 18.289 registros, inputs identificados, elegibilidad, cocientes, percentiles y fallback.
- [decisions.csv](decisions.csv): selección y exclusión de cada registro, CIK, pesos y slots.
- [quarterly.csv](quarterly.csv): retornos netos, SPY/control, IC, tamaños y efectivo por fecha.
- [benchmark_periods.csv](benchmark_periods.csv): sesiones exactas y precios SPY ajustados.
- [coverage.csv](coverage.csv): cobertura y razones por fecha/división.

La nueva versión se archiva sin modificar sus filtros, pesos, Top-N, sectores, costes o ventanas para mejorar los resultados. Las pruebas #43/#44 y motores anteriores permanecen congelados. No hay evidencia para sustituir SPY con RCF ni para afirmar una estrategia demostrada.

Antes de otra hipótesis, sigue pendiente reconciliar el registro completo de búsquedas y concretar qué evidencia económica y datos acreditados sustentan el siguiente diseño. Una futura ventaja tendrá que pasar auditoría diaria y una prueba independiente fijada antes de observarla; un nuevo corte del mismo historial no satisface esa condición.

Verificación realizada: `--verify` pasa; la reproducción real en `data/research_reproductions/repurchase_cash_v1_20260929` coincide exactamente en JSON canónico completo y las cinco huellas de CSV. El motor mantiene su sello previo `116d0a49559f3ab1cf29b5af3401aed210b3f746d2644336c8f01b17b37e554f`, sin cambios después de observar rendimientos. La especificación conserva `ba8cddcae48ce672402a41401f6be1a841f1ed3ff26931bf27142a6f47eec594` y el protocolo `1ff153efac76ba9c4d65a75002bce3feadf2c92caa0724c24d79b609e087ae07`.

Los 17 tests nuevos cubren independencia de retornos/precios/emisiones, invariancia de escala, requisitos y exclusiones, clases duplicadas antes de elegibilidad, percentiles/fallback entre elegibles, efectivo por cap de división, muestra/ventanas/ambos costes, calendario incompleto, mutaciones del protocolo/motor padre, periodo inválido por retorno seleccionado ausente, control y reproducción sintética. **1.039 tests pasan** en la suite completa (ocho avisos preexistentes de correlación constante en `factor_lab`); Ruff y mypy del motor nuevo pasan. Las fuentes originales y la base operativa se preservan.
