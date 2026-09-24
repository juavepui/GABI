# Identidad histórica 2010–2015: issue #27

Auditoría local del 24 de septiembre de 2026. Antes de modificar código se
revisaron `main`, README, [#25](historical-data-audit.md),
[#26](historical-membership-2010-2026.md), `entity_master.py`,
`entity_migration.py`, `identity.py`, `edgar.py`, el esquema SQLite y los tests.
El proyecto ya tenía `entities`, aliases temporales, resolución
`resolved/ambiguous/unresolved` y protección contra ticker reciclado. Se
reutiliza esa arquitectura; no se añade un segundo mapa de entidades.

## Cobertura medida en la base operativa

La [medición JSON](historical-identity-2010-2015.json) toma los cuatro cierres
trimestrales de cada año y la composición fja05680 archivada en SQLite. Cada
porcentaje divide observaciones miembro-trimestre, no empresas únicas. La
serie de composición sigue siendo comunitaria y [discrepa](historical-membership-2010-2026.md)
de la otra fuente histórica. `CIK candidato` significa una sola fila efectiva
del mapping lawcal; **no equivale a identidad acreditada**.

| Año | Miembro-trimestre | CIK candidato único | CIK y entity_id acreditados | Alias válido en fecha | Nombre histórico SEC ligado al alias |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2010 | 1.992 | 94,53% | 0,201% | 0,201% | 0,201% |
| 2011 | 1.988 | 95,02% | 0,201% | 0,201% | 0,201% |
| 2012 | 1.988 | 96,13% | 0,201% | 0,201% | 0,201% |
| 2013 | 1.988 | 97,13% | 0,201% | 0,201% | 0,201% |
| 2014 | 1.993 | 97,69% | 0,151% | 0,151% | 0,151% |
| 2015 | 2.004 | 97,95% | 0% | 0% | 0% |

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

Se examinaron **949** instancias XBRL originales de 2010–2015 ya descargadas
en `data/history_refresh/validation_1996_2015/instances/`. En **216** hay un
único `dei:TradingSymbol` y un identificador XBRL que coincide con el CIK de la
presentación; son **33 pares ticker-CIK** distintos. **100** de esas
observaciones corresponden a un miembro de la serie fja05680 en la fecha de
presentación, y **186** contienen también el nombre del registrante en la
instancia. Otras **733** no proporcionan un ticker único utilizable y se
rechazan, sin rellenarlo desde el mapa actual.

El [catálogo CSV](historical-identity-filing-evidence.csv) conserva ticker,
CIK, nombre histórico si existe, fecha, accession, URL del documento SEC y
SHA-256 de cada archivo. Se importaron las 216 observaciones a
`entity_observations` como dataset `filing_identity`, con `entity_id` derivado
del CIK. La importación es idempotente y **no crea `entity_aliases` ni atribuye
precios o fundamentales**. `historical_archive.get_filing_identity_evidence`
resuelve solo el día de filing; fuera de ese día devuelve `unresolved`. Si dos
CIK aparecieran para el mismo ticker y día, devuelve `ambiguous`.
`historical_membership.constituents_as_of(fecha)` incorpora esa prueba al
miembro cuando la fecha coincide exactamente con la presentación, y muestra
el nombre histórico y URL SEC; en los demás días sigue exigiendo un alias
temporal revisado. La API legacy del backtest no utiliza esta observación como
permiso para leer precios por ticker.

De las 216 observaciones SEC, 130 concuerdan con el CIK candidato de lawcal,
80 carecen de candidato aplicable y seis discrepan. Las seis corresponden a
`ACT` en 2014–2015: SEC identifica CIK `0001578845` en esos documentos mientras
lawcal propone `0000884629`. No se ha decidido si refleja una sucesión
corporativa, una fecha incorrecta o un error de mapping. En la serie fja05680
`ACT` no figura como miembro en esos seis días. Este ejemplo muestra por qué
no se debe promover automáticamente un único CIK comunitario a alias histórico.

## Uso y límites temporales

```powershell
.venv/Scripts/python.exe -m gabi.entity_migration --activate-reviewed-symbol WLP
.venv/Scripts/python.exe -m gabi.historical_identity_audit --scan-instances --import-evidence --output docs/historical-identity-2010-2015.json --evidence-csv docs/historical-identity-filing-evidence.csv
```

El primer comando activa solo `WLP`; el segundo lee ficheros locales y SQLite,
sin solicitudes de red, y archiva las pruebas SEC. Repetirlos conserva una
observación por accession, CIK y símbolo. La fecha de presentación prueba el ticker en ese documento,
**no** la fecha exacta de entrada/salida del índice ni un intervalo continuo
de cotización. `valid_from` y `valid_to` permanecen reservados a los aliases
que tengan evidencia de sus límites; no se fabrican a partir de dos filings.

La [SEC](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
ofrece gratuitamente submissions y XBRL por CIK. El archivo actual solo contiene
una muestra de las instancias originales; cubrir los aproximadamente 500
miembros por trimestre exige revisar más portadas, cambios corporativos y
fuentes de fechas efectivas. Los nombres parecidos o nombres anteriores de
SEC no se usan para fusionar entidades. Un adquirente conserva su CIK distinto;
un ticker reutilizado nunca hereda datos atribuidos al emisor anterior. La
reentrada del mismo ticker en el índice se representa como otro intervalo de
pertenencia, independiente de la identidad del emisor.

Queda trabajo para completar el #27: revisar otros tickers retrospectivos de
las dos fuentes de composición; obtener portadas y avisos de cambio para los
miembros sin prueba directa; y atribuir precios/filings legacy por CIK antes
de activar más aliases en la base operativa. El 0,2% acreditado demuestra que
la extracción local y la corrección puntual funcionan, pero **no certifica**
el universo 2010–2015 ni habilita aún un backtest fundamental completo.
