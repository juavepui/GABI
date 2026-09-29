# Auditoría de inputs de asignación de capital (#60)

Fecha: 2026-09-29. Esta etapa reconstruye datos y mide cobertura; **no calcula scores, retornos, IC ni estrategias**. No añade configuraciones al ensayo QV/QVM/QE ni modifica sus resultados, motores o pruebas ciegas #43/#44.

## Fuentes y universo

Se conservan las 57 fechas y las empresas elegibles de los rankings originales 2011–2025, con sus identidades CIK. Se verifican las huellas originales y el snapshot de 3,47 GB (`5e3beb94ed05ca4067d09d9c125dffe2215578a0863b79666856cd168980974c`). Solo se abre SQLite con `mode=ro`, sin helpers que creen tablas. Los facts proceden exclusivamente de `entity_observations`, atribuidos al CIK y a la URL Company Facts de ese emisor; no se buscan por ticker ni se mezclan empresas por aliases.

Los metadatos de filings se reconstruyen desde los 68 archivos SEC SUB de 2009–2025 ya conservados y fijados por el suplemento SIC. Se verifican los ZIP y se exige registrante primario. SUB proporciona cierre fiscal, filing, aceptación y accession. La documentación de [SEC Company Facts](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) indica que su API agrega hechos de taxonomías estándar aplicables a toda la entidad; no equivale a cobertura completa de etiquetas custom. Los [archivos SEC](https://www.sec.gov/data-research/sec-markets-data/financial-statement-data-sets) permiten contrastar los metadatos. No se convierten NUM.ddate/qtrs redondeados en periodos exactos.

## Reglas fijadas antes del cálculo de cobertura

1. Por CIK/fecha, seleccionar el último 10-K o 10-K/A **presentado y aceptado en fechas anteriores** a la señal, con orden filing, aceptación y accession. No consultar etiquetas actuales, filings futuros ni resultados bursátiles. Un filing nuevo sin las partidas requeridas no permite rescatar el ejercicio anterior.
2. Usar su cierre fiscal SUB exacto. Exigir cierre anterior al filing y señal, edad ≤550 días. Facts: mismo accession, mismo emisor, misma fecha de presentación/form que SUB y FP=FY. Annual cash flows en USD, con diferencia entre inicio/fin de 330–400 días, cierre exactamente igual al periodo SUB. No usar un dato trimestral aunque venga en un 10-K, ni combinar ejercicios o restatements de filings distintos.
3. Conservar separadamente `PaymentsForRepurchaseOfCommonStock`, `ProceedsFromIssuanceOfCommonStock` y `ProceedsFromStockOptionsExercised`. Las dos primeras solo se restan cuando sus inicios y cierres coinciden exactamente. No usar recompras de common+preferred como sustituto, no sumar opciones sin evidencia de no solapamiento, ni usar un componente de opciones como total de emisión.
4. Una ausencia permanece ausente; un cero explícito se conserva. Valores de flujo no finitos, negativos en partidas de cobros/pagos o duplicados contradictorios invalidan la partida. La diferencia de las dos líneas se etiqueta **proxy parcial de flujos comunes**, no payout neto total ni shareholder yield acreditado.
5. OCF (`NetCashProvidedByUsedInOperatingActivities`) y capex (`PaymentsToAcquirePropertyPlantAndEquipment`) se conservan con sus periodos. FCF=OCF−capex solo con ambas partidas en el mismo periodo; OCF puede ser negativo, capex no. No imputar capex cero ni convertir OCF de operaciones continuadas en OCF total.
6. Acciones: exclusivamente `CommonStockSharesOutstanding`, USD excluido, instantes de cierre actual y cierre previo a 330–400 días, **en el mismo filing**. La portada `EntityCommonStockSharesOutstanding` no se mezcla con el balance. Se publica el cociente bruto si hay una única pareja positiva, pero **no se declara dilución ajustada por splits**: el snapshot no contiene splits atribuidos a entidades y la ausencia en su tabla de ticker no demuestra que no hubo ninguno. La base homogénea debe acreditarse antes de usar la señal; no se asume factor uno.
7. Conservar valores, periodos exactos, accession, emisor, filing/aceptación, URL, hash de payload y motivos de exclusión. Reportar cobertura por fecha, ventana fija y división SIC, incluido el denominador completo original. Cada símbolo-fecha conserva una fila, también cuando faltan datos; los recuentos de disponibilidad se deduplican por CIK para que dos clases de acciones no sean dos empresas independientes. No sustituir falta de fuente por falta de actividad económica.

## Decisión de viabilidad

Para considerar investigable el proxy emparejado y/o FCF se exige ≥30 empresas válidas en ≥30 fechas, incluyendo ≥8 fechas en cada ventana 2011–15/2016–20/2021–25. Es una puerta de **tamaño de muestra**, no de rentabilidad ni ausencia de sesgo. Se publican además discrepancias de periodos, signos, filings, duplicados y edad. No se cambian reglas para aumentar cobertura.

Una familia de inversión posterior tendrá que fijar hipótesis económica, inputs admitidos, normalización por capitalización acreditada, sesgos de selección, costes y corrección por búsqueda **antes** de medir rendimiento. La emisión total y la dilución ajustada quedan fuera mientras no se resuelvan su completitud y base de splits. No hay promoción a Investor ni alteración del catálogo de evidencia.

## Reproducibilidad

El protocolo, especificación y motor se fijan con SHA-256 antes de la auditoría completa. Se conservan `annual_inputs.csv`, `facts_used.csv`, `coverage.csv` y `filing_periods.csv`, más resultado/huellas/versions. La publicación no se sobrescribe. `--verify` comprueba sellos y artefactos; `--reproduce DIRECTORIO` repite el cálculo completo en otra carpeta. Ninguno descarga fuentes ni escribe en la base operativa.
