# Actualizaciones incrementales locales (#55)

Se amplían los actualizadores existentes de GABI y la tarea local de #46. El scheduler sigue siendo `gabi.periodic_tasks`; los checkpoints y eventos se guardan en la misma SQLite local. No se añade un servicio remoto.

## Auditoría y política de cada fuente

| Fuente | Antes | Actualización normal y revisiones |
|---|---|---|
| Yahoo, precios | Una fecha máxima global decidía descargar dos años para todo el universo; upsert de todas las filas | Checkpoint por entidad/ticker. Desde el último cierre válido menos 14 días naturales; agrupación de tickers con la misma fecha inicial. Sólo se escriben observaciones nuevas o modificadas. Una sesión ya consultada no se vuelve a pedir durante 24 h. |
| Yahoo, ajustes | El refresco podía corregir sólo una ventana del histórico | Un cambio en `Adj Close / Close`, o en el nivel común de Close ajustado por splits, exige reparar desde el inicio de la serie cacheada. La reparación falla si omite observaciones ya existentes; no escribe una mezcla de ajustes. |
| Yahoo, fundamentales | Snapshots con TTL y reintento limitado | Se conserva el TTL. Se identifica snapshot nuevo/revisado/idéntico con hash y se mide la operación. El proveedor no ofrece una consulta incremental de este snapshot: cuando vence se pide de nuevo. |
| SEC, XBRL | Companyfacts completo y reconstrucción de todas sus observaciones en cada refresco vencido | Primero submissions. Si filings y hechos disponibles no cambian, se evita companyfacts y su reconstrucción. Auditoría semanal de hechos y reconsulta de filings recientes durante dos días para cubrir retrasos de publicación. Hash idéntico evita reprocesar; de lo contrario sólo se escriben hechos nuevos/revisados por `(tag, unit, start, end, accession)`. |
| SEC, identidad | Mapeo ticker/CIK cacheado sin caducidad | Revisión semanal, reemplazo atómico y fallback a caché tras error. Checkpoints de hechos separados por CIK; se conserva `filed_date`, accession y provenance. La adquisición histórica/as-of conserva su ruta explícita. |
| FRED | Hasta 260 observaciones recientes, reescritas al vencer el TTL | Ventana desde la última observación menos 400 días, con auditoría completa cada 30 días. Sólo se escriben deltas; valores retirados (`.`) se guardan como NULL. La política cubre revisiones antiguas mediante esa auditoría periódica. |
| Tiingo, archivo | La descarga ya reanudaba por fichero, pero la importación recorría y reinsertaba todos | JSON escrito mediante fichero temporal y rename. Hash/checkpoint por símbolo y ventana; sólo se parsean/importan ficheros pendientes. Una revisión de un snapshot fijado se rechaza y necesita un ID de fuente nuevo. Se conserva la cola y el tratamiento del cupo mensual de #44. |
| Universo vivo | El job lo forzaba en cada ejecución | Revisión diaria con checkpoint/hash. Una caché usada tras fallo no se registra como composición nueva acreditada. |

Companyfacts entrega todos los conceptos de una empresa en una respuesta; no se finge que la API permita un delta por fecha. La reducción consiste en evitar la descarga cuando submissions no cambian y en escribir únicamente los hechos que cambiaron. [API oficial SEC](https://www.sec.gov/search-filings/edgar-application-programming-interfaces).

El rango de FRED usa `observation_start`; `units` conserva la transformación configurada, incluida la inflación interanual. Las series macro son contexto actual revisado, **no vintages point-in-time para backtests**. [Parámetros oficiales FRED](https://fred.stlouisfed.org/docs/api/fred/series_observations.html).

## Reanudación y trazabilidad

Los checkpoints avanzan después de persistir observaciones válidas. Un fallo conserva la última marca válida y fuerza un reintento; una interrupción entre escritura y checkpoint repite una comparación idempotente, sin duplicar datos. `new`, `revised`, `unchanged` y `failed` aparecen en `sync_events`, con conteos independientes de filas nuevas/revisadas, motivo, llamadas lógicas, tamaño de payload, duración y CPU del hilo. El job añade duración y CPU total del proceso.

Los reintentos transitorios son acotados, con backoff y `Retry-After` limitado a 30 s. La cadencia se comparte entre workers; SEC no tiene cuatro limitadores independientes. Tiingo conserva su ritmo y espera por cuota existentes. No se guardan claves API en los eventos. Los artefactos/preregistros y resultados prospectivos no se recalculan con este cambio.

`python -m gabi.periodic_tasks --run` hace mantenimiento incremental. `--run --full-refresh` solicita deliberadamente el histórico completo de precios y auditorías completas de SEC/FRED/fundamentales. El archivo Tiingo sigue fijado: ese flag no sobrescribe snapshots históricos. El refresco manual de la app fuerza una consulta actual, pero conserva la ventana incremental salvo reparación de ajustes.

Los catorce días de precios y los 400 días de FRED son ventanas de detección, no garantías de que una revisión más antigua aparezca inmediatamente. FRED revisa todas las fechas mensualmente; precios permiten una auditoría completa explícita y reparan ajustes detectados. Los datos rechazados conservan el estado anterior y quedan registrados como fallo.

## Medición reproducible, sin red

`python scripts/benchmark_incremental_sync.py` usa bases temporales aisladas, 20 tickers sintéticos y 503 sesiones XNYS, con cuatro cierres nuevos por ticker. Nunca toca `data/gabi.db`. Resultado de esta máquina en `benchmark.json`:

| Métrica | Ventana anterior | Incremental | Repetición misma sesión |
|---|---:|---:|---:|
| Invocaciones yfinance | 1 batch | 1 batch | 0 |
| Filas devueltas | 10.060 | 260 | 0 |
| Payload estimado (CSV por ticker) | 433.360 B | 11.960 B | 0 B |
| Filas escritas | 10.060 | 80 | 0 |
| Filas realmente nuevas | 80 | 80 | 0 |
| Duración local | 0,395 s | 0,780 s | 0,281 s |
| CPU del proceso | 0,172 s | 0,313 s | 0,172 s |

La ventana reduce un 97,24 % el payload estimado y un 99,20 % las escrituras. En esta prueba pequeña el primer refresco incremental usa más CPU y tiempo local por validación/checkpoints; no se promete una aceleración de CPU. No se mide latencia ni tráfico real de red: yfinance oculta sus peticiones HTTP internas, y sus invocaciones no equivalen a una sola petición por batch. Los tiempos son una medición descriptiva, sin umbrales de rendimiento en tests.

Validación enfocada: checkpoints, repetición sin red, revisiones vs altas, reparación de ajustes, payload inválido, interrupción después de escritura, reanudación de SEC, valores retirados por FRED, límites de cuota Tiingo, hashes de archivo y conexión con #46. Las pruebas se ejecutan con bases aisladas y proveedores simulados.

Los módulos modificados pasan Ruff y los nuevos adaptadores/checkpoints pasan mypy. Los controles globales conservan las tres incidencias de imports y 25 de tipos preexistentes de `factor_zoo.py`, `placebo_engine.py` y `tail_effect_test.py`, ya documentadas en #50. No se ha alterado el código preregistrado de esas pruebas para esta tarea operativa.

Comprobaciones realizadas: batería completa de 926 pruebas superadas (ocho avisos preexistentes por correlaciones de entradas constantes); 101 pruebas enfocadas de integración/identidad y 30 comprobaciones finales de checkpoints/tareas, incluido el fallo del universo añadido al final. Smoke test: 95 módulos importados y 18 archivos de la app compilados. No se ejecutó el mantenimiento contra proveedores reales ni se reanalizó la prueba #44 durante esta implementación.
