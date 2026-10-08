# F7.9: evidencia local de emisores históricos

Continúa [F7.8](f7-historical-runners.md) con los lectores de frames SEC,
submissions y nombres oficiales usados por las auditorías de identidad y
precios. No cambia horizontes, reglas de acreditación ni motores sellados.

## Responsabilidades

`domain/research/issuer_evidence.listing_life` calcula vida de cotización,
sucesiones, silencio de filings y ausencia posterior de float sobre páginas
y hechos explícitos. Conserva fechas, formularios, nombres, símbolos y URL.
`application/research/historical_issuer_evidence` coordina lectura local y
cálculo con un puerto concreto. No importa proveedores ni módulos planos.

`HistoricalIssuerFiles` implementa ese puerto con directorios y presupuestos
por instancia. Las auditorías de precios preparan los CIK de cada composición
antes de sus comprobaciones. La auditoría de identidad prepara los candidatos
que se solapan con membresía. Solo se indexan hechos de esos emisores y del
horizonte solicitado; no se crea un índice global de todos los CIK.

Las fachadas conservan `issuer_facts`, `listing_life` y el agregado explícito
`load_frames`. Ya no usan `functools.cache`. El consumidor de viabilidad
small/mid que requiere el agregado conserva su interfaz y queda pendiente de
migrar a selección por ventanas. La ausencia de una página solapada sigue
devolviendo evidencia ausente; un CIK de submissions contradictorio ahora
falla explícitamente. Los nombres de páginas no pueden escapar del directorio.

La cadena oficial de nombres usa un lector por operación, verifica CIK y
calcula SHA-256 sobre los mismos bytes acotados que interpreta. Su hash y URL
conservan el contrato anterior y no requieren una segunda lectura completa.

## Presupuestos e invalidación

Valores por defecto: archivos JSON de hasta 8 MiB, 100.000 filas por frame o
conjunto de filings, 100 páginas por emisor, catálogo de 2.000 archivos y lotes
de 1.000 CIK. Los hechos preparados tienen un máximo de 250.000 filas y un
presupuesto de 256 MiB calculado como JSON serializado más 1.024 bytes por
registro. Esta carga conservadora no pretende medir RSS. La caché LRU de bytes
fuente admite 8 MiB y no conserva árboles JSON completos.

Preparar un lote compara tamaño, mtime y ctime de los archivos conocidos,
incluidas ausencias. Un cambio, alta o borrado invalida el índice de hechos.
Las consultas de CIK ya preparados reutilizan esa instantánea; no vuelven a
examinar todo el catálogo por cada comprobación. Preparar otro lote o iniciar
otra instancia observa revisiones. Las páginas y nombres se validan por sus
metadatos en cada lectura. No se calculan hashes de todo el catálogo para
invalidar caché. Esta política presupone que las escrituras locales cambian
los metadatos del archivo; no detecta una manipulación que restaure todos ellos.

Se rechazan cambios del catálogo durante la preparación y archivos modificados
durante su lectura. Superar un presupuesto produce error, sin publicar hechos
parciales ni truncar evidencia. Los límites también se aplican al agregado de
compatibilidad: cargas mayores requieren un presupuesto explícito o la
migración de ese consumidor. Las consultas no crean directorios, escriben
SQLite ni descargan. Las acciones de descarga existentes siguen siendo
explícitas y permanecen fuera de estos lectores.

## Paridad y medición

La fixture anterior `historical_runners_migration.json` contiene la
implementación completa previa de evidencia. Quince pruebas nuevas verifican
igualdad de hechos, agregado y vida de cotización en tres horizontes, páginas
históricas, hashes, revisiones, aislamiento de instancias, copias de resultados,
límites, ausencia de efectos y rechazo de CIK/rutas contradictorios. Los tests
existentes se conectan al puerto/factoría explícito y usan archivos temporales.

Validación: suite completa de 1.799 pruebas correcta; 112 comprobaciones
finales de los flujos y arquitectura, más las 15 pruebas de lectores tras los
últimos ajustes de límites/rutas. Arquitectura backend sin nuevas excepciones,
frontend y sus nueve pruebas correctos. Mypy no añade diagnósticos a los 25
históricos exactos de motores congelados. Los tres motores CI y los 18
motores/configuraciones publicados conservan sus hashes. Ruff pasa en los
592 archivos Python de código, tests y scripts; `ruff check .` sigue detectando
errores en copias/fixtures pytest temporales del workspace, que no se alteran.
`git diff --check` correcto.

Medición reproducible:
`.venv/Scripts/python.exe scripts/measure_f7_issuer_reads.py`.
Windows/Python 3.13, 105 archivos sintéticos, 200 emisores disponibles y 20
solicitados, horizonte 2013. Cuatro ejecuciones por variante, con igualdad exacta
de resultados, sin datos reales, descargas ni holdouts. Ejecución concurrente
con tests; se mide memoria Python, no RSS.

| Variante | Primera ejecución (s) | Mediana posterior (s) | Pico Python (MiB) | Hechos indexados |
| --- | --- | --- | --- | --- |
| Caché global anterior | 1,1101 | 0,0135 | 8,3938 | 21.000 |
| Preparación por CIK | 1,4822 | 0,0529 | 10,3839 | 1.680 |

La nueva caché retiene 1.542.055 bytes de fuentes y comprueba metadatos en cada
preparación. Indexar menos hechos no garantiza menor pico total: caché fuente,
copias de resultados y comprobaciones añaden coste. No se presenta este cambio
estructural como aceleración ni reducción demostrada de memoria.

## Pendiente

[F7.10](f7-sec-archive-download.md) extrae el adaptador común de archivos y
procedencia usado por las descargas. Permanecen su selección/coordinación y
transporte HTTP de compatibilidad, las acciones de ingesta/escaneo de
`historical_identity_audit`, el agregado de
viabilidad small/mid y las lecturas generales de `storage`. El contexto global
de `historical_pit.accredited_periods` sigue siendo compatibilidad. No se declara
migrado todo `historical_*` ni resuelta #60.
