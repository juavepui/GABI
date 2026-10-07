# Selección SEC e identidad histórica por lotes (F7.5)

`application/market/sec_selection.py` coordina selección, resoluciones y errores
para worker/CLI y la fachada `edgar.ensure_edgar_data`. Recibe repositorio,
resoluciones, mapa, descarga, clasificador de errores, reloj y límites explícitos.
`domain/market/sec_selection.py` conserva las reglas de antigüedad y cobertura.
No se cambia configuración global por operación.

## Comportamiento conservado

La ruta actual deduplica símbolos, selecciona métricas ausentes o caducadas,
ausencia de hechos, fallos del checkpoint del emisor correspondiente y forzado.
La frontera de TTL sigue siendo estricta (`edad > límite`); el valor cero usa
el TTL configurado, como la interfaz anterior. El refresco completo fuerza el
mapa y la auditoría XBRL. Un fallo de mapa usa resoluciones persistidas cuando
existen. La resolución mantiene el respaldo ticker con punto/guion.

La ruta `as_of` resuelve aliases vigentes para ese día. Si no hay claims,
consulta evidencia de filing del día e intervalos acreditados del período
histórico explícito. No usa el mapa actual para resolver identidad histórica.
Los conflictos, confianza y exclusión entre emisores siguen la política
capturada. La política acreditada está en `domain/market/sec_identity.py`; las
fachadas `historical_membership` y `historical_pit` también delegan en ella.
El núcleo de identidad y otros lectores históricos siguen pendientes.

La cobertura histórica consulta existencia de hechos por emisor sin cargar
sus JSON. Los emisores sin cobertura o forzados usan descarga completa, sin
checkpoints incrementales. `fetch_complete` comparte extracción y métricas
del dominio; los enlaces de filings siguen siendo opcionales ante error de
fuente. Una respuesta que declara otro CIK falla antes de escribir.
`SqliteXbrl` conserva la transacción única de hechos, atribución y métricas.
El pool explícito admite hasta cuatro workers y conserva errores por símbolo
y el callback publicado de progreso. No mantiene conexiones durante la red.

## Consultas y límites

`SqliteSecSelection` recibe ruta y reloj. Usa SQLite de solo lectura para
selección y cobertura; una DB ausente o sin tablas no crea directorios ni
esquemas. Selecciona únicamente símbolos/datasets solicitados, en lotes de
200, con límite de 1.000 símbolos, 50.000 filas por consulta, 16 MiB por
consulta y 16 KiB por campo. La resolución histórica comprueba además filas
y bytes acumulados entre lotes. El motor SQLite limita el tamaño materializado
de filas; evidencia y checkpoints se filtran por tamaño antes de decodificar.
Un exceso falla, sin truncar resultados.

`SqliteCikResolutions` lee y recuerda resoluciones por lotes; la escritura de
las resoluciones seleccionadas usa una transacción. La acción explícita de
refresco puede persistir estas resoluciones y errores. Los errores mantienen
fuente `sec_edgar`, reloj de operación y retención de 90 días, sin inicializar
esquemas ajenos. Las consultas independientes no ejecutan esta escritura.

## Validación y medida

La referencia capturada en `fixtures/sec_selection_migration.json` corresponde
a `b840faed03356b02706803555ce20590337b8ece`. Los tests comparan selección,
flags, resoluciones, errores y progreso en TTL, forzado, fallo de mapa,
checkpoint de otro emisor, ausencia de cobertura y ruta histórica. Comparan
la política acreditada y la lectura de aliases reciclados/intervalos con la
implementación anterior, en SQLite temporal. Comprueban límites, retención,
consultas sin mutación, composición del worker y descarga completa.

Medida reproducible desde la raíz:
`.venv/Scripts/python.exe scripts/measure_f7_sec_selection.py`.
Windows/Python 3.13; 250 símbolos sintéticos, 250 observaciones atribuidas,
225 resoluciones de mapa y 25 de respaldo. Una ejecución fría y tres
repeticiones, cero descargas. Se comparan resultados, llamadas de selección
y resoluciones persistidas. El pico mide asignaciones Python, no RSS.

| Recorrido | Mediana anterior → nueva (s) | Pico anterior → nuevo (MiB) | Conexiones anterior → nuevas | SELECT anterior → nuevos |
| --- | --- | --- | --- | --- |
| Selección actual caducada | 1,0929 → 0,4625 | 0,1806 → 0,1795 | 133 → 3 | 28 → 9 |
| Datos actuales vigentes | 0,0150 → 0,0235 | 0,0799 → 0,1098 | 3 → 2 | 3 → 9 |
| Selección histórica | 2,5015 → 0,0345 | 0,1790 → 0,2048 | 500 → 2 | 500 → 6 |

La selección actual caducada y la histórica reducen conexiones y tiempo en
esta fixture. La consulta de datos vigentes aumenta tiempo, asignaciones y
SELECT por las lecturas acotadas y resoluciones en lote. La medición excluye
red y descarga; no demuestra una mejora general para emisores reales ni
para toda la ingesta. No cambian motores congelados ni excepciones de arquitectura.
