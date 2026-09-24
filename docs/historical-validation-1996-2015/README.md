# Validación histórica de GABI: 1996–2015

Esta entrega completa la descarga de los 28 paquetes estructurados de SEC de
2009–2015 para los CIK candidatos del universo histórico, recupera contextos de
informes originales que faltaban, prueba un extractor anterior a XBRL y mide
la cobertura trimestral. **No certifica un universo completo libre de sesgos ni
ejecuta un nuevo backtest de rentabilidad.**

Los datos se guardan en `data/gabi.db`, como los años posteriores. Descargas,
copia previa de SQLite e informes detallados permanecen en
`data/history_refresh/validation_1996_2015/`, excluidos de Git.

## Datos estructurados de 2009–2015

Los paquetes oficiales aportan 14.372 presentaciones de 638 CIK y 454.341 filas
de conceptos usados por GABI. Se importan datos consolidados de taxonomías
estándar; segmentos y coemisores se contabilizan como exclusiones, no se suman
a la matriz. El paquete 2009Q1 contiene solo cabeceras, conforme a la documentación
de SEC. Los primeros informes de esta colección son de abril de 2009.

La [documentación SEC](https://www.sec.gov/files/financial-statement-data-sets.pdf)
especifica que `ddate` se redondea al cierre mensual más próximo y `qtrs` al
número entero de trimestres. Por eso `sec_bulk_facts` guarda ambos campos sin
fabricar una fecha inicial ni considerarlos fechas exactas. Se descargan las
instancias XBRL originales para los informes ausentes de la caché, conservando
los contextos consolidados, su emisor, unidad y fechas exactas. Valores
contradictorios dentro del mismo contexto se excluyen.

Para reproducir el periodo mensual de NUM, los días 1–15 se asignan al mes
anterior y los posteriores al mes actual. Se ha contrastado esta convención con
los contextos originales de Costco y AutoZone, incluidos cierres del 14 y 15 de
febrero: no equivale siempre a escoger el final de mes más cercano por distancia
en días. Esta normalización solo afecta a la conciliación.

La conciliación compara importes por CIK, accession, concepto, unidad y periodo
redondeado. Distingue coincidencias, importes diferentes y ausencia de contexto
exacto. No sobrescribe cifras para forzar coincidencias ni confunde una cifra
comparativa publicada después con información conocida en el año al que se refiere.
La tolerancia es absoluta de 0,0001 unidades, sin tolerancia relativa que oculte
diferencias en importes grandes. Los **454.341 registros concilian**, sin contextos
pendientes ni valores diferentes. Es una comprobación de ingestión entre
representaciones de los mismos informes SEC, no una auditoría independiente de
la veracidad de sus cuentas.

Además de los ZIP, se han recuperado **998 instancias originales XBRL**
(31.955 hechos aceptados; 13 documentos sin conceptos aceptables) y los Company
Facts de **60 CIK** con huecos (50.546 hechos). Ninguna descarga quedó fallida.
Ambos grupos se solapan con datos existentes y entre sí: el aumento neto de
observaciones de fundamentales atribuidas a emisores es **69.975**, de 1.346.008
a 1.415.983. Los 1.377.954 registros de la antigua tabla por ticker no cambian.

Se corrigió una colisión de claves en la importación: dos cifras de efectivo de
CONSOL Energy, accession `0001070412-12-000008`, tienen el mismo mes redondeado,
pero contextos originales distintos (2008-12-31 y 2009-01-02). Ambas filas se
conservan, incluyendo el importe en la clave; no se elige arbitrariamente una.
Los [contextos originales](bulk_conflict_contexts.json) explican por qué había
454.340 claves sin importe y 454.341 registros que conservar. El suplemento
aporta 33 contextos exactos adicionales; se comprobó que deja idénticas las
métricas de ese emisor en los 80 trimestres y no modifica la cobertura publicada
([comprobación](coverage_supplement_check.json)).

## Piloto de extracción de 1996–2008

Se han revisado tres documentos originales:

| Empresa | Presentación | Formato | Hechos extraídos | Comprobaciones de transcripción |
| --- | --- | --- | ---: | ---: |
| Microsoft | 1996-09-27 | SGML con tablas de texto | 22 | 5 |
| Lehman Brothers | 2008-01-29 | HTML | 20 | 6 |
| Apple | 2008-11-05 | HTML | 29 | 7 |

El piloto incluye un emisor desaparecido. Las tablas consolidadas se seleccionan
explícitamente para evitar las tablas de segmentos, información resumida o
balances de la matriz sin consolidar. Una especificación revisada fija el hash
del documento, tabla, unidad monetaria, conceptos y periodos fiscales exactos.
El código extrae las cifras y exige superar las comprobaciones; no adivina esos
metadatos ni procesa automáticamente cualquier informe antiguo como si estuviera
validado.

Entre los controles están ingresos, beneficios, activos y flujo operativo. En
Apple y Lehman se contrastan activos, pasivos y patrimonio de la misma fecha.
Se conservan flujos negativos y ejercicios de 52/53 semanas. Las acciones
ponderadas usadas para el beneficio por acción **no** se sustituyen por acciones
en circulación. Un guion no se convierte automáticamente en cero.

Los 71 hechos quedan archivados por CIK y fecha de presentación, incluidos los
comparativos anteriores. No se crean alias históricos ni se activa la serie
actual de una empresa que reutilice el ticker. Este piloto demuestra extracción
y contraste en tres documentos; no completa todos los informes de 1996–2008.
Especificación reproducible:
[`legacy_filings_pilot.json`](../../src/gabi/resources/legacy_filings_pilot.json).

## Qué mide la cobertura trimestral

Se evalúan los 80 cierres trimestrales entre marzo de 1996 y diciembre de 2015,
con la composición de fja05680 correspondiente a cada fecha. Se muestran:

- **13 métricas calculables:** PER, P/VC, EV/EBITDA, ROIC, margen operativo,
  CAGR de ingresos y FCF a tres años, momentum de 12 meses, fuerza relativa de
  seis meses, precio/SMA200, deuda/patrimonio, volatilidad y máximo drawdown.
- **Mínimo del ranking:** al menos la mitad de las 13 métricas y algún dato
  en cada bloque Value, Quality y Momentum, como exige `scoring.py`. No es
  equivalente a cobertura completa.
- **Precios y presentación recientes:** todas las 253 sesiones NYSE previas
  y algún informe presentado en los últimos 460 días naturales. Es un control
  adicional de cobertura; no modifica los filtros de la estrategia.
- **Identidad y sector acreditados:** se muestran aparte. El mapeo comunitario
  a CIK es una pista; los sectores actuales o el SIC de un informe no se convierten
  silenciosamente en sectores GICS históricos. Sin acreditarlos, el contador de
  observaciones completamente validadas permanece en cero.

Los múltiplos indefinidos —por ejemplo, PER con pérdidas— cuentan como métrica
no calculable aunque existan las cuentas. Las ausencias se enumeran por empresa
y trimestre. Tener 13 números tampoco acredita que las fuentes sean correctas.

El diagnóstico usa hechos atribuidos explícitamente a un CIK. No rellena sus
huecos con hechos antiguos por ticker de identidad desconocida. Compara la
cobertura antes y después de esta entrega usando la copia previa, manteniendo
las mismas fuentes de precios en ambos cálculos. Por tanto, la diferencia mide
la recuperación de fundamentales, no una nueva descarga de precios ni rendimiento.

Se prefiere la serie Yahoo completa cuando tiene datos recientes suficientes;
en su defecto se usa una serie archivada completa. Nunca se empalman sus niveles.
Para múltiplos se usa cierre original del archivo o se revierten los splits
posteriores de Yahoo. Se contrastan los retornos de las fuentes donde hay al
menos 60 observaciones comunes: un percentil 99 de diferencia absoluta de hasta
0,005 se etiqueta como consistencia de solapamiento. Eso no acredita identidad
ni retornos de exclusión. Las ventanas históricas disponibles también pueden
diferir, especialmente para máximo drawdown.

## Resultados de la ejecución

Se evaluaron **39.610 observaciones empresa–trimestre** en los 80 cierres. La
tabla muestra los cierres anuales; todos los trimestres están en
[`quarterly.csv`](quarterly.csv). «Antes» es la copia tomada al iniciar esta
recuperación, con los mismos precios empleados en «después».

| Cierre | Miembros enumerados | 13 métricas antes | 13 métricas después | Mínimo del ranking antes | Mínimo del ranking después |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2009-12-31 | 499 | 0 | 0 | 19 | 20 |
| 2010-12-31 | 497 | 6 | 7 | 236 | 252 |
| 2011-12-31 | 497 | 56 | 59 | 331 | 361 |
| 2012-12-31 | 497 | 79 | 86 | 356 | 390 |
| 2013-12-31 | 497 | 85 | 94 | 365 | 400 |
| 2014-12-31 | 499 | 106 | 114 | 374 | 411 |
| 2015-12-31 | 502 | 108 | 118 | 376 | 416 |

En diciembre de 2015, las 13 métricas son calculables para **23,51%** del
universo enumerado (antes 21,51%); el mínimo del ranking alcanza **82,87%**
(antes 74,90%). Las 118 empresas con las 13 métricas también tienen las 253
sesiones previas y un informe reciente. Sumando los 80 trimestres, las
observaciones con las 13 métricas pasan de 1.708 a **1.853**, y las que cumplen
el mínimo del ranking, de 8.057 a **8.827**. Son mejoras de cobertura, no de
rentabilidad; una empresa puede contarse en varios trimestres.

Los cierres anteriores a 2009 todavía no tienen empresas que cumplan el mínimo
del ranking con hechos atribuidos a CIK. El piloto no proporciona todo el
histórico de fundamentales, acciones en circulación y crecimientos requerido.
Los comparativos conservan la fecha de publicación del documento que los aporta.

En diciembre de 2015, los mayores huecos son EV/EBITDA (228 empresas), crecimiento
de FCF a tres años (222), margen operativo (192) y ROIC (147). Esta cuenta combina
datos ausentes y métricas indefinidas según las fórmulas actuales; no se rellenan
con cero. El desglose está en [`missing-metrics.csv`](missing-metrics.csv).

La comparación de precios encuentra 391 símbolos con solapamiento consistente,
23 con discrepancias y 570 sin las 60 observaciones comunes necesarias.
[`price-validation.csv`](price-validation.csv) permite localizar cada caso.
**Ninguna observación se etiqueta como completamente validada:** todavía no
se han acreditado alias empresariales fechados ni sectores GICS anteriores a
2016. Ese cero representa controles pendientes, no demuestra que todas las
correspondencias candidatas sean incorrectas. Tampoco se han validado aquí los
retornos de exclusión de bolsa.

Para ampliar un backtest verificable, el trabajo pendiente es acreditar esas
identidades y sectores, resolver las discrepancias de precios y ampliar la
extracción de fundamentales, priorizando empresas desaparecidas y los conceptos
que faltan. Descargar todos los paquetes disponibles de SEC no equivale a
disponer de todas las métricas para todas las empresas.

Evidencia de esta ejecución:

- [`ingestion-summary.json`](ingestion-summary.json): aumento neto, recuentos por
  fuente y comprobación de integridad de SQLite (`ok`).
- [`reconciliation.json`](reconciliation.json): 454.341 coincidencias.
- [`sources.csv`](sources.csv): URL, SHA-256, tamaño y fecha de registro de cada
  descarga; los informes `bulk_report.json`, `instances_report.json` y
  `companyfacts_gaps_report.json` detallan cada importación.
- [`legacy_pilot_report.json`](legacy_pilot_report.json): resultados y enlaces a
  los tres documentos del piloto.

## Reproducción y consulta

```powershell
.venv/Scripts/python.exe -m gabi.sec_history
.venv/Scripts/python.exe -m gabi.sec_history --instances 10000
.venv/Scripts/python.exe -m gabi.sec_history --instances 10000 --quarterly
.venv/Scripts/python.exe -m gabi.legacy_filings
.venv/Scripts/python.exe -m gabi.sec_reconciliation
.venv/Scripts/python.exe -m gabi.sec_history --companyfacts-gaps
.venv/Scripts/python.exe -m gabi.sec_reconciliation
.venv/Scripts/python.exe -m gabi.sec_history --instances 10000 --unmatched
.venv/Scripts/python.exe -m gabi.sec_reconciliation
.venv/Scripts/python.exe -m gabi.historical_coverage
```

Primero se crea una copia consistente de SQLite. Los ZIP y documentos descargados
tienen hash y URL registrados; las descargas pueden reanudarse. Los datos se
guardan por fuente, sin cambiar los resultados o el snapshot congelado de 2016
en adelante. Los contadores de importación pueden incluir el mismo hecho en
varios informes; no son necesariamente observaciones económicas independientes.

La pantalla **Calidad de los datos → Archivo histórico anterior a 2016** muestra
la curva trimestral y permite descargar su CSV. El detalle por empresa queda
en `coverage/company-quarter.csv`; los originales y ese detalle no se suben a Git.

Validación de código: 679 pruebas de la suite completa antes de los últimos
ajustes; después, las 17 pruebas específicas de archivo, extracción, cobertura
y conciliación pasan, incluidas las regresiones nuevas. Ruff, mypy y compilación
de la página modificada sin errores.
