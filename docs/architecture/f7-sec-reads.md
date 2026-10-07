# Lectores EDGAR por fecha de presentación (F7.6)

`domain/market/sec_reads.py` interpreta hechos suministrados: selección de
versiones, valor conocido por fecha y reconstrucción de companyfacts.
`application/market/sec_reads.py` comparte estas operaciones mediante un puerto
de lectura específico y reutiliza `sec_facts.compute_edgar_metrics`, sin copiar
fórmulas. La fachada EDGAR delega en estos casos de uso y conserva su interfaz,
incluida la alineación fiscal explícita de los consumidores antiguos.

## Contratos conservados

- Por CIK se conservan todas las versiones con `filed_date <= corte` y
  `end_date <= corte`, formas 10-K/10-Q y sus amendments, accession y URL de
  procedencia. El orden publicado es fecha de presentación, fin de período,
  accession y tag. No se resuelve ni acredita un ticker histórico.
- Para métricas y valores históricos, el contrato anterior corta únicamente
  por fecha de presentación; no se añade un filtro de forma o fin de período.
  La reconstrucción preserva unidades, ausencias y revisiones. El cálculo de
  métricas conserva los criterios financieros ya migrados en `sec_facts`.
- El valor escalar mantiene la selección por fecha de presentación y fin de
  período sobre los tags solicitados. No se introduce una nueva prioridad
  entre tags ni se interpreta como valor anual un hecho trimestral.
- Los hechos atribuidos se ordenan por símbolo y clave. Una duplicación entre
  aliases conserva la primera atribución para la clave XBRL antes del corte
  temporal. Adelantar el filtro podría rescatar otra versión y cambiar el
  resultado histórico; esta frontera tiene una prueba específica.
- La última fecha de filing por ticker mantiene `MAX(filed_date)`, corte
  opcional y ausencia de claves sin datos; el nuevo lector procesa por lotes.

## Flujo local y límites

`SqliteSecReads` recibe ruta y presupuestos. Cada operación abre su propia
conexión `mode=ro` y `query_only`, sin crear DB, directorios o esquemas, ni
contactar fuentes. La consulta por ticker filtra fecha, tags y unidad en SQL.
La consulta por CIK filtra fechas antes de decodificar sus versiones; la de
métricas atribuidas conserva el orden de deduplicación y lectura del emisor.

Los límites predeterminados son 250.000 filas, 64 MiB acumulados y 16 KiB por
fila; SQLite limita además la materialización de valores. Los JSON grandes
se detectan antes de decodificarlos. Un exceso falla sin truncar resultados.
La consulta en lote admite 1.000 símbolos y lotes de 200; el filtro de hechos
por ticker admite hasta 200 tags. No se añade caché de resultados, por lo que
una revisión del emisor se observa en la siguiente conexión.

El bootstrap de investigación compone el lector con Settings en:

```powershell
uv run --project backend python -m gabi_cli research sec-facts --cik 1 --as-of 2020-12-31
```

`--tag Revenues` puede repetirse para filtrar las versiones mostradas. Las
métricas y acciones se calculan con todos los conceptos disponibles del
emisor. El comando devuelve JSON finito con CIK, corte, versiones, métricas y
acciones, sin escribir archivos ni lanzar descargas. Versiones y métricas del
comando proceden de un único SELECT del emisor; un commit concurrente no mezcla
revisiones entre ambas salidas. Una caché ausente devuelve
hechos vacíos y métricas ausentes.

Los consumidores legacy conservan sus adaptadores SQL/globales, y su
inicialización histórica de esquemas, como compatibilidad. La consulta nueva
no los usa. Quedan pendientes la migración de esos lectores de compatibilidad,
otros flujos históricos y el núcleo de identidad; no se presenta este bloque
como eliminación completa de `edgar.py`. No cambian límites de arquitectura,
excepciones ni motores/configuración congelados.

## Validación y medida

La referencia capturada es `174f944210fe0a07d0186f8d60bbe05822c9c452`.
`test_sec_reads_migration.py` compara DataFrames, companyfacts, métricas,
valores y fechas con las funciones originales en SQLite temporal. Cubre cinco
cortes, ausencia de datos, tags, USD/shares, revisiones, amendments, aliases
duplicados, otro CIK y un período posterior al corte con filing anterior.
Comprueba límites, ausencia de red/escrituras y composición del comando sin
lectores legacy.

Medida reproducible:
`.venv/Scripts/python.exe scripts/measure_f7_sec_reads.py`.
Windows/Python 3.13, un emisor, 3.000 hechos en cada tabla fuente, corte
2020-12-31, ejecución fría y tres repeticiones adicionales. Cero descargas;
paridad exacta de resultados. El pico mide asignaciones Python, no RSS.

| Consulta | Frío anterior → nuevo (s) | Mediana caliente (s) | Pico Python (MiB) | Filas de hechos leídas |
| --- | --- | --- | --- | --- |
| Métricas por ticker | 0,2611 → 0,2050 | 0,2350 → 0,1831 | 2,3109 → 0,8559 | 3.000 → 1.200 |
| Métricas atribuidas | 0,4128 → 0,3980 | 0,3281 → 0,3118 | 5,0695 → 5,2926 | 3.000 → 3.000 |
| Versiones por CIK | 0,0764 → 0,0866 | 0,0774 → 0,0827 | 2,0466 → 2,0470 | 1.200 → 1.200 |

Cada consulta usa una conexión antes y después; los SELECT pasan de uno a dos
por el inventario de tablas (dos filas de metadatos adicionales en esta fixture).
Las métricas por ticker reducen materialización. La consulta de versiones
aumenta tiempo y las métricas atribuidas aumentan asignaciones. Los tiempos
son observaciones de esta fixture, no una mejora general de la ingesta ni
una predicción para datos reales o consultas durante un refresco concurrente.
