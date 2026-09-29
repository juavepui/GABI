# Primera búsqueda de una estrategia superior al S&P 500

**Estado: objetivo pendiente. Ninguno de los tres candidatos supera la puerta de auditoría diaria fijada antes de calcular resultados.** No se propone sustituir SPY, modificar Investor ni invertir capital real con estos modelos.

Seguimiento del objetivo y siguiente tarea: [issue #60](https://github.com/juavepui/GABI/issues/60). Permanece abierta; completar este diagnóstico no equivale a encontrar una estrategia demostrada.

El propietario pidió encontrar una estrategia demostrablemente mejor que el S&P 500. Se ha empezado con tres diseños económicos sencillos, especificados y publicados antes del primer cálculo en el commit `15e74c5`, después de definir el [protocolo](PROTOCOLO.md) en `7273c55`. El [preregistro ejecutable](preregistro.json) conserva fórmulas, calendario, costes, correcciones y huellas de código/protocolo. Esto congela el nuevo ensayo; **no convierte 2011–2025, ya observado anteriormente, en una muestra independiente**.

## Qué se ha construido y probado

| Candidato | Regla |
|---|---|
| QV | Valoración + calidad persistente |
| QVM | Valoración + calidad persistente + momentum |
| QE | Calidad persistente + brecha entre crecimiento histórico de FCF y crecimiento implícito en el precio |

Pesos iguales entre bloques, percentiles dentro de divisiones SIC fechadas con fallback global declarado, hasta 20 posiciones, máximo seis por división y slots vacíos en efectivo. Las tres carteras seleccionan 20 posiciones en las 57 fechas. El universo original elegible contiene 258–353 empresas por fecha: QV/QVM puntúan 194–309 y QE 120–202, sin imputación. Se registran las 18.289 empresas-fechas originales y 54.867 decisiones individuales. Hay dos retornos ausentes en el universo, ninguno entre las selecciones; los 57 periodos de cada modelo son evaluables.

SPY se extrae del snapshot original acreditado en modo de solo lectura, con precios ajustados de entrada/salida **en las mismas sesiones exactas**. Se verificó SHA-256 del snapshot de 3,47 GB antes de leerlo. Cada periodo parte de 100.000 USD; paga compra, venta y comisiones sin deuda. Coste base: 10 pb/lado y 1 USD/operación; estrés: 25 pb/lado y 1 USD/operación. SPY soporta su propio round-trip.

## Resultados del primer diagnóstico

Las siguientes cifras son **puntos porcentuales de exceso neto medio por periodo de aproximadamente tres meses**, frente al SPY con costes comparables. No son CAGR, rentabilidades anualizadas ni rentabilidad de una cartera continua.

| Candidato | Exceso medio base | Cota inferior base | Exceso medio estrés | Cota inferior estrés | p Holm del IC | Pasa a auditoría diaria |
|---|---:|---:|---:|---:|---:|---|
| QV | +0,625 pp | −0,372 pp | +0,623 pp | −0,371 pp | 0,143 | No |
| QVM | +0,424 pp | −0,310 pp | +0,423 pp | −0,309 pp | 0,403 | No |
| QE | +0,114 pp | −0,529 pp | +0,114 pp | −0,528 pp | 0,014 | No |

Cotas inferiores de la media mediante bootstrap circular de cuatro trimestres, 5.000 réplicas, semilla 20260928, Bonferroni unilateral 0,05/3 para los tres candidatos en cada escenario. Los mismos índices se utilizan en modelos y costes. Son cotas exploratorias dentro de esta familia; no corrigen retrospectivamente todo el historial de búsquedas de GABI.

| Candidato | 2011–15 (18 periodos) | 2016–20 (20) | 2021–25 (19) |
|---|---:|---:|---:|
| QV | −0,061 pp | +1,144 pp | +0,728 pp |
| QVM | −0,038 pp | +0,606 pp | +0,670 pp |
| QE | −0,134 pp | +0,465 pp | −0,020 pp |

Ventanas fijas, exceso neto medio con coste base. Todas las carteras fallan al menos una ventana; los tres márgenes de incertidumbre admiten una ventaja negativa. QV y QVM además fallan el test de IC corregido. QE obtiene IC medio 0,0341 y p Holm 0,0141 en esta familia: indicio retrospectivo de ordenación, **sin una ventaja económica defendible de su Top-20 frente al índice**. Escogerlo únicamente por ese p contradice el protocolo y el objetivo del propietario.

## Decisión y trabajo pendiente

Los tres diseños quedan descartados **para promoción y auditoría diaria en esta versión**. No se han cambiado pesos, Top-N, filtros, sectores ni ventanas para rescatar los resultados. El histórico no permite afirmar que los diseños carezcan de toda ventaja; sí muestra que ninguno supera los criterios mínimos fijados para continuar con estas carteras.

La siguiente búsqueda debe formular un mecanismo económico adicional antes de calcularlo, comprobar primero su cobertura temporal y registrarlo como una familia nueva. Con los campos existentes se puede estudiar asignación de capital (dilución/emisiones netas, recompras y generación de caja), pero aún no se ha fijado ni probado una estrategia de esa familia. No se inferirán umbrales del resultado de este ensayo ni se anunciará una cartera ganadora al encontrar un backtest favorable. Las nuevas configuraciones se sumarán al recuento: este ensayo añade tres a las al menos 30 documentadas previamente (mínimo acumulado 33, pendiente reconciliación completa).

La lectura del módulo actual `capital_allocation.py` revela dos requisitos previos a esa familia: `shares_dilution_yoy` compara los dos últimos instantes disponibles, que no necesariamente distan un año, y `net_share_issuance_latest` puede sustituir por cero la pata ausente de emisión/recompra. Además, los últimos flujos se extraen por separado sin exigir idéntico cierre anual. No se usarán esos campos como dilución anual o payout neto acreditados. La [auditoría posterior de inputs](capital-inputs/v2/README.md) ha reconstruido por separado flujos del mismo ejercicio, conservando fecha de presentación, procedencia y ausencias. Hay muestra suficiente para el proxy parcial de flujos comunes y FCF; la dilución ajustada por splits y el net payout total siguen sin acreditar. Esta revisión no modifica la definición original ni invalida por sí sola la investigación publicada, que no usó esos campos en estos tres scores. El siguiente paso es fijar una nueva hipótesis y su normalización sobre un subconjunto declarado, antes de medir rendimiento.

Para cualquier candidato futuro que pase su descarte: auditoría de cartera diaria autofinanciada, acciones corporativas/terminales, rotación, concentración, costes y riesgo. Después, congelación de un único modelo y validación independiente/prospectiva con potencia y reglas de análisis fijadas antes de los resultados. El objetivo económico propuesto sigue siendo ≥2 pp de CAGR neto anual adicional, con volatilidad ≤110 % de SPY y drawdown no más de 5 pp peor; esta etapa trimestral **no mide ni certifica esos requisitos**.

Las pruebas #43 y #44 permanecen reservadas con sus modelos y calendarios originales. No se han leído sus resultados ni reutilizado sus muestras para esta búsqueda. La aplicación sigue siendo local y la confianza publicada de los estudios previos no cambia.

## Auditoría y reproducción

- [Resultado completo](resultado.json): inferencia, ventanas, fallos de cada modelo, versiones y huellas.
- [Scores y fallback](scores.csv): todas las empresas elegibles, bloques y modelos.
- [Decisiones](decisions.csv): selección o motivo de exclusión por empresa/fecha/modelo.
- [Panel trimestral](quarterly.csv): cobertura, IC, retornos netos y excesos.
- [SPY](benchmark_periods.csv): sesiones exactas, precios ajustados y costes.

```powershell
.venv/Scripts/python.exe -m gabi.strategy_discovery --verify
.venv/Scripts/python.exe -m gabi.strategy_discovery --reproduce data/research_reproductions/strategy_discovery_20260929
.venv/Scripts/python.exe -m pytest tests/test_strategy_discovery.py -q
```

Huella canónica del resultado: `fb633f3ace1089a1cdfa2eed6ba392097bc487cf9c25b1b49a85cb40138e5625`. Especificación: `bf6fd97c170a62f4ace184b5649451c42b2673f742515cd7bf053c986fd87682`. Motor: `2eeeb8298a30d15d61fc36e63ba353d94147bbb3280f0a61babdac23c4332e35`. Protocolo: `cc10479e2c392b42a4fef0571721f8b5def0d0d51838b2ef2eeaf5a8ec4708a3`.

La verificación comprueba fuentes y artefactos, vuelve a extraer SPY del snapshot y recalcula el resumen desde el panel publicado con lectura de floats de ida/vuelta exacta. La reproducción calcula nuevamente scores, selecciones e inferencia en una carpeta separada; nunca sobrescribe el resultado publicado. Los 11 tests nuevos cubren ausencia de datos futuros en los scores, disponibilidad mínima sin imputación, SIC/fallback, límites y empates, financiación/costes/pérdida total, fechas faltantes en HAC/bootstrap, multiplicidad, sesiones SPY exactas, rechazo de mutaciones y reproducción completa con datos sintéticos. Ruff y mypy pasan para el código nuevo.

Validación realizada: **1.007 tests pasan** en la suite completa (ocho avisos preexistentes de correlación constante en `factor_lab`); `--verify` pasa; la reproducción real en `data/research_reproductions/strategy_discovery_20260929` coincide en huella canónica del resultado y en las cuatro huellas de CSV. No se cambia el motor congelado después de ver los resultados.
