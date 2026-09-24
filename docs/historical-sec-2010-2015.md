# SEC EDGAR/XBRL 2010–2015: issue #29

Auditoría y ampliación local del 24 de septiembre de 2026. Se revisaron
`develop/main`, README, #25–#28, `edgar.py`, `sec_history.py`,
`historical_archive.py`, `historical_coverage.py`, la migración de entidades,
SQLite y tests antes de modificar código. La [API Company Facts de SEC](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
expone hechos por CIK, concepto y unidad; los
[paquetes Financial Statement Data Sets](https://www.sec.gov/data-research/sec-markets-data/financial-statement-data-sets)
contienen datos de los informes presentados. SEC redondea fechas y duraciones
en `NUM`, por lo que GABI conserva los contextos exactos de las instancias
XBRL para las consultas por fecha.

## Qué existía y qué se añadió

La base ya tenía **454.341** filas `sec_bulk_facts`, **14.372** filas de
`sec_bulk_submissions` para los paquetes históricos y **560.698** hechos
exactos atribuidos a CIK con `filed_date` en 2010–2015. `edgar_facts` guarda
por concepto valor, unidad, inicio/fin de periodo, año fiscal, formulario,
fecha de presentación y accession. `entity_observations` conserva la fuente
exacta del hecho. `compute_edgar_metrics_as_of` ya filtraba `filed_date`;
el inventario anterior de 80 trimestres ya calculaba disponibilidad numérica.
No se descargaron de nuevo paquetes ni Company Facts.

`edgar.get_issuer_facts_as_of(cik, fecha, tags=...)` consulta ahora por CIK,
incluye todas las versiones/restatements y su URL de origen, y excluye hechos
presentados después de la fecha. No usa el mapa actual de tickers ni
`period_end` como fecha de publicación. Su salida **no** acredita que una
acción concreta perteneciera al índice: esa relación se consulta por el
intervalo de identidad separado.

El extractor anual une dos tags candidatos solo cuando hay un ejercicio
común con valores USD concordantes (tolerancia fija del 1 %), mantiene la
prioridad declarada de tags, conserva la última revisión publicada —incluidas
las enmiendas 10-K/A una vez presentadas— y rechaza conflictos dentro de un
mismo filing. El CAGR de tres años y el crecimiento
interanual exigen cierres anuales consecutivos; cuatro observaciones separadas
por una década no bastan. Esto corrige un caso real de Apple: al corte de
2018 el CAGR anterior era ~101 % porque enlazaba 2008 con 2016–2018; ahora
queda ausente. Al corte de 2019, la unión acreditada entre tags recupera un
CAGR ~6,46 % con 2016–2019, que antes quedaba ausente. No se rellenan años
sin hechos SEC, ni se usan fundamentales actuales de Yahoo.

La corrección afecta también a recuentos 2016+ del inventario anterior,
porque `compute_edgar_metrics` es compartido. Recalculando exactamente las
mismas fechas y miembros del [inventario #25](historical-data-audit.md):

| Corte | CAGR ingresos disponible antes → ahora | 13 métricas antes → ahora | Mínimo ranking antes → ahora |
| --- | ---: | ---: | ---: |
| 2016-12-31 | 316 → 322 | 96 → 100 | 368 → 369 |
| 2018-12-31 | 321 → 348 | 100 → 109 | 393 → 395 |
| 2019-12-31 | 125 → 295 | 36 → 99 | 412 → 415 |
| 2020-12-31 | 352 → 393 | 132 → 145 | 421 → 422 |
| 2025-12-31 | 470 → 483 | 174 → 184 | 474 → 474 |

Son **recuentos de datos**, no retornos. El CSV del #25 sigue siendo el
snapshot anterior a esta corrección; cualquier comparación de rendimiento
2016+ debe regenerar ambos lados con el mismo código y datos antes de
interpretar diferencias.

## Cobertura al cierre de cada año

El [detalle por miembro](historical-sec-2010-2015.csv) y el
[resumen JSON](historical-sec-2010-2015.json) se regeneran sin red con
`.venv/Scripts/python.exe -m gabi.historical_sec_audit`. La composición
procede del archivo fja05680, con la corrección temporal WLP/ANTM. Cada celda
cuenta miembros con identidad acreditada y **al menos un hecho** del concepto
publicado hasta el 31 de diciembre; no equivale a tener cuatro ejercicios,
un ratio definido ni una cotización atribuida. El JSON separa también hechos
presentados en los últimos 460 días. El CSV enumera conceptos ausentes por
miembro. Identidades ambiguas o sin resolver cuentan como ausentes.

| Año | Miembros | Identidad | Ingresos | Resultado operativo | Beneficio neto | Patrimonio | Caja | Deuda LP | CFO | Capex | Acciones | D&A | Insumos ROIC | Insumos FCF |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2010 | 497 | 451 | 358 | 310 | 397 | 433 | 414 | 273 | 435 | 322 | 427 | 326 | 246 | 322 |
| 2011 | 497 | 455 | 375 | 349 | 420 | 448 | 425 | 344 | 446 | 335 | 436 | 354 | 322 | 335 |
| 2012 | 497 | 461 | 383 | 360 | 429 | 455 | 433 | 368 | 454 | 342 | 444 | 377 | 348 | 342 |
| 2013 | 497 | 463 | 396 | 362 | 435 | 459 | 438 | 378 | 458 | 349 | 447 | 382 | 361 | 349 |
| 2014 | 499 | 465 | 401 | 371 | 444 | 463 | 442 | 395 | 462 | 360 | 452 | 395 | 380 | 360 |
| 2015 | 502 | 457 | 398 | 369 | 440 | 457 | 436 | 398 | 456 | 359 | 446 | 393 | 385 | 359 |

Las primeras fechas observadas por concepto están en el JSON. Varias se
remontan a **1996 solo por un pequeño piloto de informes antiguos**; no
representan cobertura general desde 1996. En 2010–2015, los principales
huecos entre miembros acreditados son deuda, capex, D&A e ingreso/resultado
operativo según el año. `NetIncomeLoss` sustituye la necesidad de EPS para
el PER vigente, que usa beneficio total y capitalización, no EPS diluido.
`ROIC` aquí significa presencia de beneficio, patrimonio y deuda; el ratio
puede seguir indefinido o exigir fechas compatibles. No se calcula todavía
la estrategia con este inventario.

Para reproducir la segunda pasada de identidad desde la caché local y
regenerar los artefactos (el primer comando descarga solo archivos ausentes):

```powershell
.venv/Scripts/python.exe -m gabi.historical_identity_audit --fetch-unresolved-instances 58
.venv/Scripts/python.exe -m gabi.historical_identity_audit --scan-instances --import-evidence --evidence-csv docs/historical-identity-filing-evidence.csv --build-intervals --intervals-csv docs/historical-identity-intervals.csv --output docs/historical-identity-2010-2015.json
.venv/Scripts/python.exe -m gabi.historical_sec_audit
```

## Evidencia de identidad y mejora medida

El #27 ya había seleccionado y cacheado **1.751** instancias de CIK
candidatos. El #29 añadió **58** instancias 10-K/10-Q de intervalos aún sin
resolver, con la misma descarga pausada e idempotente de SEC. Once aportaron
ticker y CIK explícitos adicionales. El catálogo
[`historical-identity-filing-evidence.csv`](historical-identity-filing-evidence.csv)
contiene ahora **907** pruebas de **316** pares distintos, con fecha,
accession, URL y SHA-256. La tabla `entity_observations` dataset
`filing_identity` sigue separada de `entity_aliases`. La nueva función
`historical_archive.list_filing_identity_evidence_as_of` solo muestra pruebas
publicadas hasta la fecha consultada y marca dos CIK para el mismo ticker
como conflicto; no crea aliases.

La acreditación #27 se reejecutó sobre las 907 pruebas. Dos portadas SEC
independientes con ticker y CIK coincidentes son prueba directa aunque el
nombre abreviado del mapping comunitario no case exactamente (GE y JCP).
Para el nivel más débil, sin ticker SEC, se sigue exigiendo nombre coincidente
y al menos dos informes. Los intervalos quedaron en **199** directos,
**347** candidatos corroborados, **16** ambiguos y **33** sin resolver.

| Año | Cobertura acreditada antes del #29 | Después |
| --- | ---: | ---: |
| 2010 | 90,06 % | 90,46 % |
| 2011 | 90,64 % | 91,05 % |
| 2012 | 91,70 % | 92,10 % |
| 2013 | 92,56 % | 92,91 % |
| 2014 | 92,88 % | 93,08 % |
| 2015 | 91,92 % | 92,22 % |

La mejora no elimina las limitaciones del [#28](historical-prices-2010-2015.md):
un CIK acredita al emisor SEC, no el ajuste por dividendos, la clase de
acción ni el retorno de exclusión. Los intervalos históricos acreditados son
retrospectivos; para un backtest el valor financiero sigue limitado por la
fecha real de presentación del filing.
