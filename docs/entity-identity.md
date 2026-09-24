# Identidad persistente y migración incremental

GABI conserva las tablas por ticker para los consumidores existentes y añade
`entities`, `entity_aliases`, `entity_observations` y `entity_candidates`.
La implementación está en `gabi.identity`; `entity_master` usa esa identidad
para los snapshots y las consultas de sector.

`entity_id=cik:0001326801` identifica al registrante SEC. Sin CIK se crea un
`local:<uuid>` persistente, que el llamador debe conservar: dos nombres iguales
no se fusionan. Un CIK tampoco identifica una clase de acción. Los precios
conservan su ticker de origen y no se mezclan clases simultáneas del mismo emisor.
Una adquisición entre CIK diferentes no convierte al adquirente en la entidad
de la adquirida ni permite prolongar sus cotizaciones.

## Alias y resolución por fecha

Cada alias contiene `entity_id`, `symbol`, `valid_from`, `valid_to`, `source`
y `confidence`. Los intervalos son **[valid_from, valid_to)**; `valid_to=NULL`
expresa continuidad abierta hasta nueva evidencia. Las fechas son ISO.
El punto y guion de clases (`BRK.B`/`BRK-B`) se normalizan, sin eliminar la clase.

`identity.resolve(symbol, fecha)` devuelve `resolved`, `unresolved` o
`ambiguous`. Exige confianza >=0,9 y una sola entidad candidata. Las pruebas
contradictorias se conservan: no gana silenciosamente el registro más reciente.
Los límites abiertos requieren mantenimiento; registrar una nueva compañía con
el mismo ticker provoca ambigüedad hasta acreditar el fin de la anterior.

La semilla revisada contiene WLP→ANTM, FB→META y ANTM→ELV, con fechas y enlaces de evidencia
en `entity_migration.KNOWN_ALIASES`. No es un catálogo exhaustivo de cambios.

```python
from gabi import identity

issuer = identity.ensure_entity("1326801", "Meta Platforms")
identity.add_alias(issuer, "FB", "2012-05-18", "2022-06-09", source="URL de evidencia")
identity.add_alias(issuer, "META", "2022-06-09", source="URL de evidencia")
assert identity.resolve("FB", "2019-06-01")["entity_id"] == issuer
```

## Datos y backtests

La nueva atribución es una escritura paralela, dentro de la misma transacción
que la escritura antigua. `upsert_prices`, `upsert_splits` y
`upsert_fundamentals` aceptan `entity_id`; `upsert_edgar_facts` acepta `cik`.
La descarga SEC conserva el CIK que se pidió. Yahoo solo atribuye cuando hay
una identidad acreditada para el ticker en la fecha de descarga.

`entity_observations` conserva entidad, dataset, ticker de origen, clave natural,
payload y fuente. Así, sobrescribir una fila antigua por ticker no borra los
datos previamente atribuidos a otra entidad. XBRL se comparte por entidad entre
sus alias; las revisiones se siguen filtrando por `filed_date`. Los fundamentales
Yahoo mantienen la fecha de descarga y no se usan como fundamentales históricos.

El ranking histórico es **no estricto por defecto** (`strict_identity=False`,
igual que `entity_master.get_sector_asof`): `data/gabi.db` solo tiene activados
los intervalos revisados de `WLP` de 2009–2014, sin precios atribuidos. Exigir
identidad acreditada por defecto dejaría los backtests sin cobertura suficiente.
Por eso los símbolos sin alias registrado siguen leyendo de la caché
legacy por ticker, exactamente como antes de esta migración; `identity_status`
en la tabla resultante marca cada fila como `resolved`/`ambiguous`/`unresolved`
para que quede visible, no oculto. El sector se busca entre snapshots de esa
entidad; una foto posterior solo es una aproximación de sector, nunca una
prueba de que el ticker pertenecía a esa empresa en el pasado.

V1/V2 consultan precios y filings atribuidos para las entidades seleccionadas.
V2 conserva el propietario de las posiciones abiertas y falla si faltan precios
atribuidos, en vez de valorar una compañía con las cotizaciones de otra.
No se implementa contabilidad de canjes de fusiones ni retorno de exclusión.
Un periodo sin precio de salida acreditado se rechaza; eso debe leerse junto con
el diagnóstico de periodos excluidos, no como rentabilidad de todo el universo.

La preparación de precios históricos puede usar el ticker sucesor inequívoco
de la misma entidad. No descarga bajo un ticker reciclado para rellenar a su
antigua compañía. Una serie completa del sucesor puede respaldar el periodo
anterior; no se empalman automáticamente series con ajustes distintos ni clases
simultáneas. Si hay varias series incompletas, se requiere una serie consistente
atribuida. Los cambios de ticker no se convierten automáticamente en operaciones
corporativas sin coste dentro de la contabilidad de cartera.

`strict_identity=True` en el ranking exige identidad acreditada y excluye a
los símbolos sin alias -- útil una vez completada la migración/atribución de
`data/gabi.db`, no antes. Los adaptadores de módulos aún no migrados conservan
la API legacy, pero no pasan por encima de alias conocidos o conflictivos.
SPY conserva su tratamiento explícito como benchmark; no se generaliza esa
excepción a acciones.

## Migración SQLite

Con la aplicación cerrada, ejecutar desde el proyecto:

```powershell
uv run python -m gabi.entity_migration --migrate
```

Antes de migrar una base existente, el CLI crea una copia SQLite consistente
`data/gabi.db.before-identity.bak` si todavía no existe. La migración es aditiva
e idempotente. Importa los snapshots con CIK como evidencia **solo del día
observado**, copia su sector y registra los seis intervalos revisados. No toca las
filas financieras originales. Esa copia es previa a la primera migración; para
un punto de restauración más reciente hay que hacer otra copia con otro nombre.

Los datos legacy no tienen CIK por fila: atribuir todo el histórico al último
`edgar_metrics.cik` podría consagrar una contaminación anterior. Se pueden
redescargar por CIK o atribuir explícitamente después de verificar la procedencia:

```powershell
uv run python -m gabi.entity_migration --attribute-symbol META --entity-id cik:0001326801 --dataset prices --source "archivo/proveedor y evidencia revisada"
```

`--start` inclusivo y `--end` exclusivo permiten limitar el intervalo de datos.
Para precios/splits filtran la fecha de mercado; para XBRL, `filed_date`; para
fundamentales, la descarga. Se admiten `prices`, `splits`, `fundamentals` y
`edgar_facts`. La herramienta no puede verificar por sí misma la afirmación
introducida en `--source`; no debe usarse para atribuir automáticamente todos los
tickers. Las lecturas por fecha requieren también alias acreditados.

La entrega original ejecutó el informe sobre `data/identity-audit.db`, una base
separada con la semilla revisada. El #27 activó selectivamente `WLP` en
`data/gabi.db`; no migró los demás alias ni atribuyó precios/fundamentales.
Al activar las lecturas estrictas, la cobertura útil baja hasta acreditar alias
y atribuir/redescargar datos. La UI lo muestra como ausencia, no como calidad verde.

## Fallback histórico investigado

La [API de submissions de SEC](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
ofrece nombres anteriores, metadatos y enlaces a filings por CIK. También existe
un archivo bulk de submissions; no hace falta un proveedor comercial. Los nombres
anteriores no dan por sí solos intervalos de cotización de los tickers.

`import_submissions_candidates` compara nombre actual y `formerNames` con un
nombre histórico conocido, normalizando mayúsculas y puntuación. Guarda una
candidata auditable, nunca un alias confirmado. Se puede importar un JSON local:

```powershell
uv run python -m gabi.entity_migration --submissions-json submissions.json --candidate-symbol OLD --historical-name "Nombre histórico" --source "URL del JSON SEC"
```

La portada de un filing con CIK y ticker permite `import_filing_identity` para
ese día. Extenderlo a un intervalo requiere evidencia adicional de cotización o
cambio de ticker; las fechas de `formerNames` no se usan como sustituto. No se
infiere el CIK del prefijo de un accession, que puede corresponder al presentador.
El CSV de composición histórica local trae tickers, sin nombres: por eso este
fallback no puede resolver automáticamente todos sus símbolos. No se descargó
el bulk ni se hizo una campaña masiva de resolución en esta iteración.

Fuentes revisadas para las semillas: [inicio de FB](https://www.sec.gov/Archives/edgar/data/1326801/000132680114000007/fb-12312013x10k.htm),
[cambio a META](https://www.sec.gov/Archives/edgar/data/1326801/000132680123000052/meta-12312022x10kars.htm),
[cambio a ANTM, aviso del mercado](https://www.miaxglobal.com/alert/2014/12/02/miax-corporate-action-alert-wellpoint-inc-wlp-name-and-symbol-change-anthem),
[cambio a ELV](https://www.sec.gov/Archives/edgar/data/1156039/000115603922000081/elv-20220630.htm).

## Cobertura medida y límites

El artefacto [identity-coverage.json](identity-coverage.json) fija los hashes de
ambos CSV y cuenta símbolos distintos y pares símbolo/fecha de composición.
La medición usa los CSV locales, no cifras del mercado actual consultadas en red.

| Universo local | Símbolos distintos | Sin correspondencia antes | Después de la semilla |
|---|---:|---:|---:|
| 1996-01-02 a 2025-08-23 | 1.126 | 454 (40,32%) | 452 (40,14%) |
| Desde 2016-01-04 | 690 | 123 (17,83%) | 121 (17,54%) |

La mejora recupera FB y ANTM. Es una mejora pequeña y medible; no elimina el
problema histórico. El ~16% de partida no se reproduce exactamente con estos
archivos y denominadores. «Después» mantiene las coincidencias léxicas del mapa
actual como candidatas y añade los símbolos recuperados por evidencia temporal;
**no convierte esas coincidencias en identidades históricas acreditadas**.

Con solo esta semilla hay 2.843/1.644.637 pares históricos acreditados (0,173%).
Desde 2016 hay 2.498/622.161 (0,402%). El resto carece de prueba temporal en esta
base de auditoría. Tener CIK tampoco asegura disponer de precios ni XBRL atribuidos.
La calidad del propio histórico de composición continúa siendo una limitación.

La [auditoría específica de 2010–2015](historical-identity-2010-2015.md)
cuantifica esa brecha sobre los miembros trimestrales y archiva pruebas directas
de ticker/CIK en XBRL original. Esas pruebas son de un solo día de filing y no
activan aliases continuos en la base operativa.

Para repetir sobre una base de auditoría nueva:

```powershell
uv run python -m gabi.entity_migration --db data/identity-audit.db --migrate --report docs/identity-coverage.json
```

Calidad de los datos permite diagnosticar por fecha entidades sin CIK,
resoluciones ambiguas y candidatas por nombre. Los tests usan SQLite temporal y
bloquean red en los casos de identidad, incluyendo cambios reales, exclusión,
reciclaje sintético, clases de acción, rollback y determinismo de la huella.
