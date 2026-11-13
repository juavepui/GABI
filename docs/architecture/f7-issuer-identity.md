# Identidad de emisores y series acreditadas (F7.6)

`identity.py` conserva la interfaz usada por ranking histórico, ingesta,
preparación y motores congelados. Las reglas de normalización, definición de
entidad, inmutabilidad del CIK, validez de alias y selección de una serie
atribuida viven en `domain/market/identity.py`. Los casos de uso de consulta,
sucesores, últimas fechas de filing y precios de backtest reciben puertos
explícitos en `application/market/identity.py`.

## Almacenamiento y contratos

`SqliteIdentityReads` comparte la resolución por lotes que antes pertenecía a
`SqliteSecSelection`. La selección SEC reutiliza ese lector. Las consultas de
identidad y membresía acreditada ya no inicializan tablas: usan conexiones
`mode=ro`, `query_only` y transacción de lectura por conexión. Base o tabla
ausente equivale a ausencia de evidencia. No hay fallback al mapa CIK actual.

Se conservan las fronteras inclusiva/exclusiva de los alias, el umbral 0,9 y
la ambigüedad ante cualquier reclamación contradictoria, incluso de baja
confianza. Sin alias operativo vigente, la resolución solo admite los niveles
acreditados del período activo; una prueba de filing aislada no se eleva a
intervalo acreditado. Un alias registrado pero no resuelto bloquea la vuelta
a hechos o precios legacy del ticker.

Una serie pertenece a una entidad y conserva su ticker de procedencia.
Se prefiere el ticker solicitado; solo un alias alternativo no concurrente
puede sustituirlo. Se excluyen observaciones fuera de la vida acreditada del
emisor y dentro de intervalos conflictivos. No se concatenan clases de acciones.
La lectura atribuida conserva el histórico necesario para tenencia; el ranking
corta por fecha en su caso de uso. La elección de sucesor recibe `today`
explícito y conserva el orden de preferencia anterior.

El guard de últimos filings agrega por entidad en SQL, por lotes, sin
materializar los JSON de todos los hechos. Considera todas las atribuciones,
sin deduplicarlas como las métricas SEC: un duplicado antiguo no puede ocultar
la última fecha visible. Solo los símbolos sin ningún alias registrado usan
la tabla legacy. Este fallback conserva el símbolo original de la consulta.

Los límites del lector son 1.000 símbolos, lotes de 200, 50.000 filas y 16 MiB
por consulta, con campos de 16 KiB. La fachada mantiene un presupuesto de
250.000 filas y 64 MiB para observaciones. El exceso falla sin truncar. Los
payloads se comprueban antes de decodificar y los agregados de hechos también
rechazan payloads sobredimensionados. Cada nueva conexión observa revisiones;
no hay caché de identidad. Las fases de un caso de uso que abre varias
conexiones no constituyen una única revisión global del universo.

`SqliteIdentityWrites` recibe ruta, reloj y generador de identificadores.
Las escrituras de entidad, alias y candidato son explícitas. `ensure_schema`
y `put_observations` operan sobre la conexión del llamador y no hacen commit:
precios/fundamentales legacy y observaciones atribuidas mantienen su rollback
conjunto. Una corrección XBRL bajo otro alias sustituye la copia de la misma
clave del emisor. `SqliteXbrl` reutiliza estas funciones directamente; se retira
`infrastructure/legacy/sec_xbrl.py`.

El fingerprint de atribución sigue siendo una operación probatoria explícita,
fuera de consultas de ranking. Recorre las cuatro tablas ordenadas mediante
cursor y alimenta el SHA-256 con los mismos bytes JSON canónicos. No carga toda
la base en una estructura Python ni inicializa esquemas. No se sustituye por
mtime, TTL o fecha máxima.

## Otros flujos históricos

`domain/research/historical_pit.py` conserva elegibilidad de ventanas, prioridad
de fuentes, cierre negociado y liquidación terminal. Los casos de uso de
`application/research/historical_pit.py` reciben lector, productores activos,
fechas trimestrales y ventana previa explícitos. `SqliteHistoricalPit` lee
provenance, precios, splits y eventos terminales sin escrituras de esquema.

Se mantienen las ventanas trimestrales rechazadas, el horizonte de tenencia,
la prioridad Yahoo, las fuentes manuales sin productor y los metadatos de serie.
Las liquidaciones conservan salida negociada, sucesión acreditada 1:1,
contraprestación en efectivo y salida no estricta cuando falta evidencia.
La consulta de ranking decodifica la procedencia una vez por emisor y evita
otra consulta por intervalo. Los precios se acotan por fuente, símbolo e
intervalo, con límites de 25.000 filas y 16 MiB; la evidencia admite hasta 1 MiB
por campo. No se mezclan fuentes ni se rellenan huecos.

La resolución de identidad en membresía histórica filtra símbolos y fecha en
SQL, en lugar de cargar todas las pruebas de filing de la base.
[F7.8](f7-historical-runners.md) migra runners, exportaciones históricos y el
respaldo operativo por ticker de backtests; [F7.9](f7-historical-issuer-files.md)
extrae los archivos/cachés de evidencia. Conservan pendientes las descargas
y las lecturas generales de `storage`. Los loaders de composición y los escritores de
`historical_archive`/`historical_price_policy` se extraen en
[F7.7](f7-historical-composition-writes.md). El contexto global `accredited_periods` sigue siendo
compatibilidad; los casos de uso nuevos reciben parámetros. No se declara
completamente migrado el ranking ni se modifican motores sellados.

## Validación y medida

`fixtures/identity_migration.json` captura `identity.py` y `historical_pit.py`
de `77a6c2aeb9ef` (el campo `commit` conserva el SHA completo). Las pruebas
comparan resolución, series y atributos, sucesores, observaciones, últimas
fechas, fingerprint, ventanas, prioridad de fuente, splits y liquidaciones.
Además prohíben conexiones legacy y red, verifican ausencia de creación de DB,
observación de correcciones, límites y rollback de doble escritura.

Validación: suite completa de 1.760 pruebas Python correcta; comprobación
posterior de 64 pruebas de identidad/selección y 13 pruebas de paridad correcta.
Arquitectura backend/frontend, nueve pruebas de arquitectura frontend, lint,
tipos y hashes de los motores/configuración congelados correctos. El inventario
retira seis dependencias legacy de esta fase y no añade excepciones.

Medida reproducible: `.venv/Scripts/python.exe scripts/measure_f7_identity.py`.
Windows/Python 3.13, 200 símbolos sintéticos, 20.000 hechos y una fixture
separada de 782 precios acreditados, cuatro ejecuciones por variante, sin datos
reales ni descargas; resultados, atributos de serie y hash idénticos.
Ejecutada junto a otras comprobaciones; tiempos observados, sin promesa general.

| Flujo | Frío anterior → nuevo (s) | Mediana caliente (s) | Pico Python (MiB) | Conexiones | SELECT | Filas entregadas a Python |
| --- | --- | --- | --- | --- | --- | --- |
| Últimos filings | 6,5373 → 0,1386 | 6,9094 → 0,1408 | 0,4676 → 0,1965 | 400 → 3 | 400 → 5 | 20.200 → 412 |
| Fingerprint explícito | 0,8866 → 1,8231 | 0,9309 → 1,7641 | 24,7694 → 0,0069 | 1 → 1 | 4 → 5 | 20.400 → 20.404 |
| Serie de ranking acreditada | 0,0456 → 0,0481 | 0,0323 → 0,0502 | 0,1751 → 0,1536 | 3 → 2 | 3 → 4 | 784 → 799 |

Las filas nuevas incluyen el inventario de tablas por conexión (cuatro tablas
en la fixture de identidad y ocho en la histórica);
el agregado sigue examinando los hechos del emisor dentro de SQLite. El hash
recorre todos los registros y es más lento en esta fixture; reduce memoria
Python, no acredita menor I/O ni mide RSS. La serie acreditada reduce conexiones
y evita releer evidencia por intervalo, pero tarda más en esta fixture.
