# Identidad histórica 2010–2015: issue #27

Auditoría local del 24 de septiembre de 2026. Antes de modificar código se
revisaron `main`, README, [#25](historical-data-audit.md),
[#26](historical-membership-2010-2026.md), `entity_master.py`,
`entity_migration.py`, `identity.py`, `edgar.py`, el esquema SQLite y los tests.
El proyecto ya tenía `entities`, aliases temporales, resolución
`resolved/ambiguous/unresolved` y protección contra ticker reciclado. Se
reutiliza esa arquitectura; no se añade un segundo mapa de entidades.

## Cobertura medida

La [medición JSON](historical-identity-2010-2015.json) toma los cuatro cierres
trimestrales de cada año y la composición fja05680 archivada en SQLite. Cada
porcentaje divide observaciones miembro-trimestre, no empresas únicas. La
serie de composición sigue siendo comunitaria y [discrepa](historical-membership-2010-2026.md)
de la otra fuente histórica. `CIK candidato` significa una sola fila efectiva
del mapping lawcal; **no equivale a identidad acreditada**. La segunda fase
conserva dos niveles adicionales, distintos del alias operativo:

- `confirmed_by_multiple_evidence`: al menos dos portadas XBRL originales, en
  fechas distintas, declaran el **mismo ticker y CIK**, y el nombre de la empresa
  coincide con la candidata. Se acota por los intervalos de pertenencia y de
  la candidata; sigue siendo una reconstrucción retrospectiva.
- `corroborated_candidate`: un solo CIK candidato en todo el intervalo, al
  menos dos 10-K/10-Q SEC del mismo CIK en fechas distintas y nombre coincidente
  con el informe o con la cadena oficial de nombres SEC. **Los informes no
  declaran necesariamente el ticker**: este nivel es menos fuerte que el
  anterior y nunca se convierte en alias operativo automáticamente.

| Año | Miembro-trimestre | CIK candidato único | Ticker+CIK SEC repetido | Candidato corroborado sin ticker SEC | Total acreditado por niveles | Ambiguo |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2010 | 1.992 | 94,53% | 33,28% | 57,18% | 90,46% | 1,91% |
| 2011 | 1.988 | 95,02% | 33,05% | 58,00% | 91,05% | 2,01% |
| 2012 | 1.988 | 96,13% | 33,65% | 58,45% | 92,10% | 2,01% |
| 2013 | 1.988 | 97,13% | 33,95% | 58,95% | 92,91% | 2,21% |
| 2014 | 1.993 | 97,69% | 33,52% | 59,56% | 93,08% | 2,56% |
| 2015 | 2.004 | 97,95% | 33,63% | 58,58% | 92,22% | 2,65% |

> Actualización #28: las nominaciones revisadas de
> `resources/historical_identity_corrections_2010_2015.json`, el nivel
> `confirmed_historical_ticker` y el rechazo de CIK sucesores elevan el total
> acreditado a 97,4–98,8 % y reducen el ambiguo a 0,3–0,45 %; véase
> [precios 2010–2015](historical-prices-2010-2015.md#identidad). La tabla
> anterior conserva el estado de #27/#29.

El 95% propuesto **no se alcanza**. El total del último nivel solo sirve para
filtrar candidatos de investigación; no equivale a cobertura de precios,
fundamentales point-in-time ni composición oficial del índice. Para una prueba
que exija ticker confirmado directamente por SEC, el nivel pertinente es la
columna del 33–34%, no el total. El usuario aceptó el 90–93% como suficiente
para continuar; los conflictos siguen explícitamente excluidos.

Antes del #27, la base operativa tenía **0% de aliases fechados** para estos
miembros. Se activaron solo dos intervalos revisados de `WLP` que abarcan
2009-12-01 a 2014-12-03; por eso ahora hay un miembro-trimestre acreditado en
casi todos los trimestres de 2010–2014. La semilla FB→META y ANTM→ELV ya
existía, pero **no** se activó en la base operativa: hacerlo sin atribuir también
los precios y hechos legacy por entidad haría que el ranking dejase de utilizar
esas series. El mapping lawcal se
construye desde revisiones de Wikipedia; su autor explica que los CIK anteriores
a 2014 se completaron manualmente y que algunas fechas de entrada/salida son
aproximadas. Se mantienen como candidatos incluso cuando el CIK es único.

Las dos series de composición etiquetan retrospectivamente a WellPoint como
`ANTM` en 2010. La [nota SEC de diciembre de 2009](https://www.sec.gov/Archives/edgar/data/1156039/000119312509244519/dex991.htm)
identifica el ticker `WLP`, y el [aviso MIAX](https://www.miaxglobal.com/alert/2014/12/02/miax-corporate-action-alert-wellpoint-inc-wlp-name-and-symbol-change-anthem)
fija el cambio a `ANTM` el 2014-12-03. La consulta temporal sustituye solo
esa etiqueta entre ambas fechas, muestra `label_corrections` y deja los CSV
originales intactos. En el backtest 2016–2025 no se cambia ningún ticker.

## Evidencia directa recuperada de SEC

Se examinaron **2.632** instancias XBRL originales de 2010–2015 en
`data/history_refresh/validation_1996_2015/instances/`. La segunda fase
seleccionó 1.751 informes de los CIK candidatos y descargó los que faltaban;
el #29 recuperó otras 58 instancias dentro de intervalos aún sin resolver.
el parser también reconoce el espacio de nombres DEI antiguo `xbrl.us/dei`.
En **907** instancias hay un
único `dei:TradingSymbol` y un identificador XBRL que coincide con el CIK de la
presentación; son **316 pares ticker-CIK** distintos. **733** de esas
observaciones corresponden a un miembro de la serie fja05680 en la fecha de
presentación. Las **907** tienen nombre del registrante, tomado de DEI o,
si falta ahí, del índice estructurado SEC `SUB` del mismo accession. Otras
**1.723** no proporcionan ticker único utilizable; dos fallan la comprobación
de CIK/XML. Se rechazan sin rellenarlas desde el mapa actual.

El [catálogo CSV](historical-identity-filing-evidence.csv) conserva ticker,
CIK, nombre histórico si existe, fecha, accession, URL del documento SEC y
SHA-256 de cada archivo. Se importaron las 907 observaciones a
`entity_observations` como dataset `filing_identity`, con `entity_id` derivado
del CIK. La importación es idempotente y **no crea `entity_aliases` ni atribuye
precios o fundamentales**. `historical_archive.get_filing_identity_evidence`
resuelve solo el día de filing; fuera de ese día devuelve `unresolved`. Si dos
CIK aparecieran para el mismo ticker y día, devuelve `ambiguous`.
`historical_membership.constituents_as_of(fecha)` incorpora esa prueba al
miembro cuando la fecha coincide exactamente con la presentación, y muestra
el nombre histórico y URL SEC; en los demás días sigue exigiendo un alias
temporal revisado o un intervalo de investigación corroborado. La API legacy
del backtest no utiliza esta observación como permiso para leer precios por ticker.

De las 907 observaciones SEC, 808 concuerdan con el CIK candidato de lawcal,
90 carecen de candidato aplicable, tres coinciden con un candidato múltiple y
seis discrepan. Las seis corresponden a
`ACT` en 2014–2015: SEC identifica CIK `0001578845` en esos documentos mientras
lawcal propone `0000884629`. No se ha decidido si refleja una sucesión
corporativa, una fecha incorrecta o un error de mapping. En la serie fja05680
`ACT` no figura como miembro en esos seis días. Este ejemplo muestra por qué
no se debe promover automáticamente un único CIK comunitario a alias histórico.

## Intervalos y conflictos

El [CSV de intervalos](historical-identity-intervals.csv) conserva
`valid_from` inclusivo, `valid_to` exclusivo, CIK, estado, recuentos de
pruebas directas y de informes del emisor, y referencias SEC con URL y SHA-256.
Se archivan 595 intervalos: **199** con ticker+CIK SEC repetido, **347**
candidatos corroborados, **16** ambiguos y **33** sin pruebas suficientes.
`historical_membership.constituents_as_of` expone `identity_tier`,
`accredited_symbols` y `excluded_identity_symbols`. Dos CIK candidatos que se
solapan, una prueba SEC de otro CIK para el ticker o un ticker diferente
declarado por el mismo CIK dentro del intervalo bloquean la acreditación.
Esto puede excluir también clases de acción legítimas; requiere revisión.

El estado de `ACT` sigue conflictivo. Otros casos como `CB`/`ACE` y
`ANDV`/`TSO` muestran por qué una etiqueta retrospectiva o el nombre actual
del emisor no basta para certificar un ticker antiguo. La ausencia de prueba
contradictoria solo se refiere al **conjunto SEC descargado**; no certifica que
no exista un documento externo sin examinar.

Los límites se recortan con entrada/salida del índice, fechas del candidato y
cambios de ticker revisados como `WLP`→`ANTM`. Algunas fechas comunitarias son
aproximadas: un intervalo corroborado es una reconstrucción posterior, no una
afirmación de que el ticker ya constaba en SEC al comienzo del intervalo. Las
reentradas generan intervalos separados. Los nombres actuales y `formerNames`
de la API SEC solo verifican la continuidad del **mismo CIK**; nunca fusionan
adquirente y adquirida ni se usan como fundamental histórico conocido entonces.

## Uso y límites temporales

```powershell
.venv/Scripts/python.exe -m gabi.entity_migration --activate-reviewed-symbol WLP
.venv/Scripts/python.exe -m gabi.historical_identity_audit --fetch-candidate-instances 2000 --output data/identity-fetch.json
.venv/Scripts/python.exe -m gabi.historical_identity_audit --scan-instances --import-evidence --build-intervals --output data/identity-before-names.json
.venv/Scripts/python.exe -m gabi.historical_identity_audit --fetch-issuer-names 100 --output data/identity-names.json
.venv/Scripts/python.exe -m gabi.historical_identity_audit --scan-instances --import-evidence --build-intervals --output docs/historical-identity-2010-2015.json --evidence-csv docs/historical-identity-filing-evidence.csv --intervals-csv docs/historical-identity-intervals.csv
```

El primer comando activa solo `WLP`. Los comandos `--fetch-*` hacen descargas
gratuitas de SEC y usan caché local, URL y SHA-256. La selección de instancias
toma como máximo tres informes repartidos por cada fila candidata, no todos
los filings. La descarga de nombres se limita a los CIK aún sin resolver.
Los comandos `--scan-instances` y `--build-intervals` no usan red y son
idempotentes. La [SEC permite acceso gratuito](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
y [limita el ritmo automático](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data)
a diez solicitudes por segundo; la descarga concurrente de instancias pauta
cuatro solicitudes por segundo y la de nombres también queda por debajo.
La fecha de presentación prueba el ticker **solo** en ese documento. El
intervalo reconstruido usa varias pruebas y límites de otras fuentes;
no se escribe en `entity_aliases` ni atribuye cotizaciones legacy.

La [SEC](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
ofrece gratuitamente submissions y XBRL por CIK. El archivo sigue siendo una
muestra dirigida, no un rastreo exhaustivo de todos los filings. Cubrir los
aproximadamente 500 miembros por trimestre exige revisar más portadas, cambios
corporativos y fuentes de fechas efectivas. Los nombres parecidos o anteriores
de SEC no fusionan entidades. Un adquirente conserva su CIK distinto;
un ticker reutilizado nunca hereda datos atribuidos al emisor anterior. La
reentrada del mismo ticker en el índice se representa como otro intervalo de
pertenencia, independiente de la identidad del emisor.

Queda trabajo para completar el #27: verificar los CIK retrospectivos sin
informes de época (`APA`, `BLK`, `CI`, `DIS`, `FTI`, `LLL`, `XOM`, `XRX` entre
otros), resolver las 16 colisiones, contrastar cambios de ticker con avisos
de mercado y revisar los 33 intervalos sin pruebas suficientes. Además hay
miembros sin CIK candidato. El 90–93% no permite declarar alcanzado el 95%.
Incluso si se alcanza, se necesitarán precios y fundamentales históricos
atribuidos por CIK antes de un backtest fundamental estricto de 2010–2015.
