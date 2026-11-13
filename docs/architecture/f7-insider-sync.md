# F7.4: sincronización explícita de Form 4

`application/market/insider_sync.py` comparte la selección de filings, lectura
de XML, parseo, decisión de frescura, persistencia, errores y progreso entre el
job moderno y la entrada de compatibilidad. Recibe documentos, resolución CIK,
almacén, clasificación de errores y reloj; no conoce SQLite, requests ni settings.

El proveedor HTTP recibe User-Agent y conserva timeout de 30 s para submissions
y 20 s para XML, el manejo de 404 y el límite de 20 Form 4. Un filing XML fallido
consume su posición dentro del límite y no tumba los restantes, como antes.
No se añaden reintentos ni se altera la política SEC durante esta extracción.

`SqliteInsiders` recibe directorio y reloj UTC. Conserva las 17 columnas,
clave `(symbol, accn, line_no)`, flags enteros, timestamp por escritura, registros
de intentos vacíos y retención de errores de 90 días. Las consultas usan SQLite
de solo lectura, no crean tablas y dividen metadatos en lotes de 500 símbolos.
La ficha conserva su límite existente de 10.000 filas.

El bootstrap CLI conecta proveedor, almacén y reloj y los inyecta al executor
del worker. Los llamadores de compatibilidad conservan la fachada que delega en
el mismo caso de uso. El puente mantiene la resolución CIK existente
de SEC, incluida la caché de símbolos retirados y sus escrituras de procedencia.
Esa resolución aún depende del arranque legacy; el worker conserva la comprobación
de directorio compatible y no modifica configuración por operación. La fachada
`insider.py` conserva sus lectores/escritores para `data_quality` y consumidores
de compatibilidad. Se retirarán junto al núcleo; no se declara migrada esa parte.

La migración conserva `max_age_hours=0` como 24 h, tal como hacía el original;
el comentario previo del job que decía forzar descarga era incorrecto. También
conserva comparación estricta `>` del TTL, timestamps futuros no caducados,
deduplicación y progreso que excluye símbolos sin CIK del contador completado.

Las referencias del original sobre SQLite temporal comparan filas, metadatos,
errores y resultado. Las pruebas cubren lote grande, lecturas sin escrituras,
fechas inválidas, intento vacío, poda, errores de fuente/escritura y política HTTP.
La medición reproducible del flujo completo usa fuentes sintéticas, 50 símbolos
y 20 transacciones por símbolo; no representa la latencia de SEC ni mide RSS.
El script compara resultados y todas las filas/fechas persistidas en cada repetición.

Resultado local (tres repeticiones tras calentamiento): mediana anterior 0,7590 s,
nueva 0,7229 s, pico Python 0,114 MiB en ambos casos. Las 1.000 transacciones y
50 metadatos coinciden exactamente. La diferencia de tiempo es pequeña; no se
presenta como optimización de red ni como mejora general de rendimiento.
