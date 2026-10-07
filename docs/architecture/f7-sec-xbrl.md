# Ingesta XBRL y almacenamiento por emisor (F7.4)

El caso de uso `application/market/sec_xbrl.py` comparte la sincronización
incremental entre la fachada `edgar_sync.run_one` y los refrescos del worker/CLI.
Recibe fuente, repositorio, checkpoints, intentos medidos, reintentos, hashes,
reloj y política de alineación fiscal explícitos. Los cálculos financieros
siguen en `domain/market/sec_facts.py`, sin duplicar fórmulas.

## Conservación y atribución

Se conservan las claves `(tag, unit, start_date, end_date, accn)` y los campos
`val, form, fp, fy, filed_date`. Un accession posterior se añade; una revisión
del mismo accession sustituye esa observación. Los hechos retirados de una
respuesta no borran observaciones ya almacenadas. La extracción mantiene USD,
shares y las etiquetas `us-gaap`/`dei`, incluidos los períodos instantáneos sin
fecha inicial y las ausencias. Los aliases repetidos entre familias conservan
la última fila de proveedor para cada clave.

`SqliteXbrl` escribe `edgar_facts`, `entity_observations` y `edgar_metrics` en una
única transacción por emisor. El CIK se valida; si la respuesta incluye CIK,
debe coincidir con el solicitado. El ticker se conserva como procedencia,
sin crear evidencia de identidad histórica ni mezclar series de precios.
El puente pequeño `infrastructure/legacy/sec_xbrl.py` reutiliza el esquema y
la atribución de `identity` sobre la conexión suministrada: no cambia settings,
no abre otra conexión ni copia su política de sustitución entre aliases.

## Auditoría, checkpoints y límites

La lista de filings decide si solicitar companyfacts: primer refresco, ausencia
de hechos/métricas, filing modificado, filing de los dos últimos días, fallo
anterior, auditoría semanal vencida o refresco completo explícito. Un hash
companyfacts idéntico omite lectura y reprocesamiento del histórico. Hashes y
watermark solo avanzan tras persistir; un fallo conserva el último éxito.
Una interrupción entre commit de datos y checkpoint se recupera mediante el
delta idempotente, sin publicar éxito anticipado.

El proveedor limita cada JSON decodificado a 64 MiB, transmite por bloques de
64 KiB, mantiene User-Agent y timeout de 30 s y cierra la respuesta antes de SQL.
Los reintentos y la cadencia SEC compartida mantienen su política publicada.
El repositorio lee exclusivamente el emisor solicitado, con límites de 250.000
filas, 64 MiB acumulados y 16 KiB por fila. Sus consultas usan conexiones de solo
lectura, no crean DB/tablas y no mantienen conexiones durante red/reintentos.
Los límites son explícitos y un exceso falla sin truncar silenciosamente.

El bootstrap común compone el nuevo sincronizador y lo inyecta en actualizaciones
de Administración, símbolos y refrescos periódicos del worker y CLI. Sigue
pendiente la selección legacy de empresas por antigüedad/cobertura, el recorrido
histórico `as_of` y su descarga no incremental, otros lectores EDGAR y el núcleo
de identidad. La fachada mantiene esos consumidores y sus contratos. No se
amplían excepciones; se retira la dependencia pandas de `edgar_sync`.
Los 18 motores/configuración congelados y artefactos publicados no cambian.

## Validación y medida

`test_sec_xbrl_migration.py` ejecuta una referencia capturada del código previo
(`3e30b943d3a7af988f7a2272da0f7e9403bd0ee7`) en bases temporales.
Compara todas las tablas, JSON/procedencia, eventos y
checkpoints en alta, hit, forzado, revisión, amendment, fallo y recuperación.
Comprueba aliases del mismo emisor, aislamiento entre CIK, CIK incorrecto,
rollback de doble escritura, límites HTTP/SQL, cierre de respuesta, consultas
sin mutación, frontera semanal y composición del worker sin ingesta legacy.

Medida reproducible desde la raíz:
`.venv/Scripts/python.exe scripts/measure_f7_sec_xbrl.py`.
Windows/Python 3.12, un emisor sintético, 1.501 observaciones, una ejecución fría
y tres repeticiones adicionales, cero descargas. Igualdad completa de las tablas
y eventos/checkpoints en cada recorrido; pico de asignaciones Python, no RSS.

| Recorrido | Mediana anterior → nueva (s) | Pico Python anterior → nuevo (MiB) | Conexiones anterior → nuevas |
| --- | --- | --- | --- |
| Ingesta inicial | 0,6385 → 0,7820 | 2,9749 → 3,0017 | 10 → 8 |
| Filings sin cambios | 0,0159 → 0,0178 | 0,0082 → 0,0096 | 7 → 7 |
| Revisión completa | 0,8260 → 0,9384 | 3,1227 → 3,0422 | 10 → 8 |

Las consultas SELECT iniciales bajan de 8 a 4; en la revisión, de 8 a 7.
La fixture registra regresiones de tiempo; no demuestra una mejora general
ni permite extrapolar a emisores reales, red, RSS o toda la base local.
