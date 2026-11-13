# Inputs de asignación de capital reconstruidos

**Auditoría completada. Hay muestra suficiente para investigar un proxy parcial de flujos comunes y FCF. No hay una nueva estrategia probada ni emisión neta total/dilución ajustada por splits acreditadas.** Seguimiento: [#60](https://github.com/juavepui/GABI/issues/60).

Se conservan las 57 fechas 2011–2025 y las 18.289 observaciones símbolo-fecha originales. Se deduplican clases de acciones para contar **18.242 emisor-fechas distintas por CIK**; esto no supone independencia estadística entre empresas o fechas. El motor inicial quedó fijado en `e6d2d1d` y abortó al encontrar fuentes fuera del alcance. La revisión de cuarentena se fijó en `99e4348` antes de reconstruir datos; no cambió periodos, tags, umbrales de cobertura ni reglas contables.

## Cobertura observada

| Dato | Empresas válidas por fecha, mínimo–máximo | Fechas con ≥30 empresas | Ventanas 2011–15 / 2016–20 / 2021–25 | Puerta de muestra |
|---|---:|---:|---|---|
| Recompras y emisión común emparejadas | 36–55 | 57/57 | 18 / 20 / 19 | Pasa |
| FCF: OCF menos capex emparejados | 126–218 | 57/57 | 18 / 20 / 19 | Pasa |
| Disponibilidad conjunta de ambos pares | 23–43 | 43/57 | 11 / 14 / 18 | Pasa |
| Dilución ajustada por splits acreditada | 0 | 0/57 | 0 / 0 / 0 | No pasa |

La puerta fijada exige ≥30 emisores en ≥30 fechas y ≥8 fechas en cada ventana; **solo evalúa tamaño de muestra**. No acredita rentabilidad, potencia suficiente para detectar una ventaja concreta ni ausencia de sesgos.

Hay 2.712 emisor-fechas con la pareja de líneas de recompras/emisión, un **14,87 %** del universo condicionado. FCF está disponible en 9.975 (**54,68 %**). No se interpreta el resto como empresa sin recompras, emisión o capex: sus datos faltan o no cumplen el contexto requerido. Un modelo futuro no podría presentarse como una prueba sobre todo el S&P 500.

| Ventana | Emisor-fechas originales | Parejas recompras/emisión | Parejas FCF | Filing seleccionado en cuarentena |
|---|---:|---:|---:|---:|
| 2011–15 | 5.455 | 816 | 2.864 | 79 |
| 2016–20 | 6.342 | 981 | 3.168 | 9 |
| 2021–25 | 6.445 | 915 | 3.943 | 0 |

## Qué se ha corregido en la reconstrucción

El [protocolo inicial](../PROTOCOLO.md) y la [revisión de procedencia](PROTOCOLO.md) exigen:

- Último 10-K/10-K/A conocido antes de la señal, filing y aceptación fechados, cierre fiscal SUB exacto y edad ≤550 días. Sin rescatar el filing anterior cuando el nuevo no contiene las partidas.
- Emisor, accession, fecha/form/FP y periodo anual exacto compatibles; duración de 330–400 días. Sin combinar ejercicios, trimestres, contextos ni restatements de filings distintos.
- Ausencias como ausencias, ceros explícitos como ceros. Sin convertir pagos negativos en positivos con `abs` ni resolver duplicados contradictorios por orden arbitrario.
- Recompras de acciones ordinarias, emisión ordinaria y ejercicio de opciones separados. La diferencia de las dos primeras es **un proxy parcial de líneas de cash flow**, no net payout total. No se suman opciones sin probar que las partidas no se solapan.
- FCF calculado con OCF total y capex conocidos en el mismo periodo, sin suponer capex cero. OCF negativo se conserva.
- Comparación de acciones de cierre actual y cierre previo anual en el mismo filing, sin mezclar la portada con el balance ni trimestres consecutivos. Los 10.045 cocientes brutos disponibles quedan identificados como **base de splits no verificada**; no se usan como dilución acreditada.

La cobertura conjunta indica disponibilidad de ambos pares. Cualquier ratio que relacione pagos con FCF debe exigir además igualdad de inicio entre los cuatro facts, así como fin y accession; no basta con que ambos escalares estén presentes. En las 1.869 emisor-fechas con ambos pares se comprobó que no hay discrepancias de inicio; esa condición tendrá que imponerse también en el futuro motor de estrategia.

## Procedencia y exclusiones

Se verificaron el snapshot original de 3,47 GB y los 68 ZIP SEC ya fijados por el suplemento SIC. Solo se leyó SQLite con `mode=ro`, sin descargar fuentes, tocar la base operativa ni leer resultados de las pruebas #43/#44. La [documentación SEC de Company Facts](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) delimita su cobertura a taxonomías estándar y datos de la entidad; no resuelve etiquetas custom ni completa partidas ausentes.

De 291.177 facts relevantes para estos emisores, 290.027 tienen la URL Company Facts exacta del CIK y **1.150 se conservan en cuarentena** por otra procedencia. Se bloquean 159 accessions, incluidos siete con mezcla de fuentes admitidas/no admitidas: quedan 289.963 facts de fuente utilizable. El bloqueo afecta al filing seleccionado en 88 emisor-fechas de 13 emisores. Son observaciones fuera del alcance, no una declaración de que las instancias SEC originales sean falsas.

La exclusión afecta sobre todo a 2011–15 y a emisores recuperados de documentos históricos. Este posible sesgo de selección debe declararse o resolverse acreditando las instancias antes de interpretar cualquier ensayo futuro. El dato ausente y la muestra reducida son límites materiales, aunque la puerta numérica pase.

En las emisor-fechas, la reconstrucción rechaza 19 valores de recompra y 80 de emisión por no cumplir la regla predefinida de signo/valor; 92 y 44 respectivamente por metadatos incompatibles. Los restantes motivos y las filas completas se conservan para auditoría. La publicación contiene 8.804 metadatos de filings anuales y 18.582 facts utilizados, con hashes individuales.

## Decisión y siguiente ensayo

Esta etapa de #60 queda completada como **reconstrucción y medición de cobertura**. La hipótesis siguiente puede estudiar recompras y generación de caja, usando únicamente partidas comparables. Antes de medir rendimiento hay que fijar el modelo y su fundamento económico, validar la normalización por tamaño/precio cuando corresponda, declarar el subconjunto y la selección de fuentes, y establecer costes, corrección por búsqueda y puerta de promoción. Debe evitarse llamar shareholder yield a este proxy incompleto.

La dilución ajustada permanece bloqueada y la emisión neta total no está acreditada. Resolver splits y completitud/solapamiento de emisión será trabajo separado; no se rellenará con cero ni con la serie por ticker. El ensayo QV/QVM/QE, Investor, el catálogo de evidencia y las reservas #43/#44 permanecen intactos. **Cero configuraciones de inversión añadidas por esta auditoría**: el mínimo documentado de 33 sigue sin convertirse en una validación independiente.

## Artefactos y comprobación

- [Resultado y huellas](resultado.json).
- [Inputs por empresa y fecha](annual_inputs.csv): valores, periodos y motivos.
- [Facts utilizados](facts_used.csv): payload hash, CIK, accession, fecha y URL.
- [Cobertura por fecha y división SIC](coverage.csv).
- [Metadatos y cierre fiscal exacto de filings](filing_periods.csv).
- [Facts fuera del alcance](source_quarantine.csv).
- [Preregistro](preregistro.json).

```powershell
.venv/Scripts/python.exe -m gabi.capital_input_audit_v2 --verify
.venv/Scripts/python.exe -m gabi.capital_input_audit_v2 --reproduce data/research_reproductions/capital_input_audit_v2_20260929
```

Resultado canónico: `a75cb5d24429d44a8696155a839c30d61ef22ecb4c0b420abd1b716e9b1e419e`. Especificación v2: `bba90b70b2ebf991396296c147d3149e8dee3d6136aa5667b64dba100a73d7a3`. Motor v2: `fc3d8da588aab1694440eebb2fd50ff8e8ad4389e6ca0e71147dceb9fdfecd87`. Motor anual v1: `6ee1bd74ab9415f2501137a5e1cc052aaee62b9c74e8f69e4b1e201c3a9dcd6a`.

La suite completa pasa: **1.022 tests**, con los ocho avisos preexistentes de correlación constante. Los 15 tests nuevos comprueban integridad temporal, mismo periodo/filing, tratamiento de cero/ausencia y signos, cuarentena, deduplicación de clases, ausencia de falsas declaraciones de rendimiento, hashes/solo lectura, mutaciones y reproducción con fuentes sintéticas. Ruff y mypy pasan para ambos motores nuevos.

La verificación real pasa. La reproducción completa en `data/research_reproductions/capital_input_audit_v2_20260929` coincide exactamente en el resultado canónico y en las cinco huellas de CSV. Los motores y sus protocolos permanecen iguales a los fijados antes del cálculo.
