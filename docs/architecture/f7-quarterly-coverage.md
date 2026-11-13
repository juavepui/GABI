# F7.4: cobertura trimestral 1996–2015

Se retira `historical_coverage.py`. El comando actual es
`gabi_cli research quarterly-coverage`, con DB, snapshot anterior, mapa CIK y
directorio de salida explícitos. El bootstrap compone conexiones de solo lectura,
calendario XNYS y escritor de los cinco artefactos. No hay backtest ni descargas.

El dominio conserva la selección Yahoo/archivo, reconstrucción nominal por
splits, ingredientes SEC/técnicos, cobertura, frescura, identidad y ausencias.
El CIK candidato exige unicidad anterior a 2016 y ausencia de conflictos con
mapas actual/cacheado; el piloto revisado sigue siendo candidato, sin activar
aliases. Las comprobaciones de identidad, sector y validación integral mantienen
su significado conservador. Las reglas de candidatos se comparten también con
la fachada `historical_archive` hasta migrar sus consumidores.

El caso de uso calcula una empresa en sus revisiones y conserva solo sus filas
de resultado; luego recompone el orden original por trimestre y membresía,
incluidos duplicados. No precarga todos los precios/hechos de SQLite. Precios
admiten 25.000 filas por serie, hechos/snapshots/aliases 100.000 por lectura,
archivos 2 MB y targets 1.000. Los excesos fallan antes de publicar. No se recorta
el historial usado para drawdown. El lector de hechos de conciliación SEC recibe
un límite total explícito de 2.000.000 y tampoco crea bases ausentes. El snapshot
documentado tiene 1.415.983 observaciones fundamentales en total; el límite cubre
ese volumen publicado incluso antes de filtrar por fecha de presentación.

No hay caché de resultados: cada comando relee sus inputs, sin cambiar DB o
snapshot. La auditoría anual sigue verificando que el detalle previo coincide
con los miembros históricos. Si los inputs cambian hay que producir un nuevo
detalle mediante una acción explícita; los informes publicados no se regeneran
ni se reesellan durante la migración.

La referencia ejecuta la fuente anterior en un namespace privado sobre bases
y archivos temporales. Sus cuatro CSV y JSON se comparan byte a byte con el
flujo actual en los 80 trimestres, con membresía duplicada, múltiples candidatos,
precios faltantes, filings futuros y snapshot de hechos vacío. Se verifica además
alcance de consultas, límites, cierre de ambas conexiones y ausencia de escrituras
en los inputs.

Medición completa reproducible:
`.venv/Scripts/python.exe scripts/measure_f7_quarterly_coverage.py`.
El arnés compara todos los artefactos en cada repetición y mide asignaciones
Python con `tracemalloc`, no RSS ni el volumen completo de los datos locales.

En Windows/Python 3.13, una pasada de calentamiento y tres repeticiones, con
13.024 precios operativos, 10.958 archivados y 160 observaciones SEC: medianas
10,9357 s original y 10,8774 s migrado; picos Python 3,306 y 4,217 MiB; 9 y 16
consultas SELECT. Los 80 trimestres/168 empresa-trimestres y los bytes de los
cinco archivos coinciden en cada pasada. En esta fixture pequeña el nuevo flujo
usa más asignaciones Python y más consultas; la entrega establece lecturas
acotadas por empresa y no acredita una mejora general de rendimiento.
