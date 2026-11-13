# F7.4: catálogo de evidencia con fuentes explícitas

`application/research/evidence_catalog.py` carga exclusivamente el catálogo
retrospectivo sellado mediante los puertos `document` y `verify_sector`. Verifica
primero reglas/manifiesto, después cada huella y la procedencia SIC. Conserva
salidas parciales y mensajes cuando falta un estudio; no abre reservas ni calcula
estudios. `domain/research/evidence_catalog.py` interpreta documentos ya verificados
y compara pesos/universo con una huella explícita de scoring. No lee archivos.

La API compone `FileEvidenceCatalog` con una raíz explícita en el bootstrap; el
adaptador de evidencia recibe ese puerto. La raíz de compatibilidad se obtiene
una vez en la composición. El ledger y el motor SIC congelado siguen usando la
fachada `gabi/evidence_catalog.py`, que delega al mismo caso de uso manteniendo
sus fuentes históricas. Por esos consumidores permanecen 79 módulos planos.
La dependencia retirada del ledger se elimina del inventario, sin excepciones nuevas.

La verificación SIC de F6 se comparte mediante `FilePublishedFactors.verify_sector`;
no se cambia el motor congelado. Un estudio ausente no impide verificar por separado
el suplemento SIC. Se mantienen fases, huellas, mensajes e interpretación
conservadora. El ledger incorpora las nuevas rutas en capturas futuras, sin
reescribir capturas ni artefactos publicados.

## Límites e invalidación

El lector acepta solamente las rutas de los siete estudios publicados y los dos
documentos del catálogo. Los JSON tienen límite de 2 MB; SIC mantiene los límites
F6 de 6 MB por archivo. La huella de scoring usa texto UTF-8, con límite de 2 MB.
No se lee `data/` ni se recorren directorios de fuentes.

La caché del lector se invalida por dispositivo, inode, tamaño, mtime y ctime de
los documentos, especificación/código/CSV SIC y scoring. Incluye archivos ausentes
para detectar su posterior creación. Comprueba los mismos stamps antes/después:
un cambio concurrente devuelve evidencia no disponible y no se cachea como verificada.
Las respuestas son copias para que un consumidor no modifique el resultado cacheado.
La caché exterior de API conserva su invalidación por revisión de ranking/pesos;
el lector revisa documentos cuando ese flujo vuelve a solicitar evidencia.

## Evidencia y medida

La fixture `evidence_catalog_migration.json` captura la salida íntegra del original
`486942a`, con SHA normalizado a LF. Siete pruebas nuevas contrastan esa referencia,
copias de publicaciones, modificaciones/borrado/restauración, tamaños/rutas, cambios
durante verificación, scope explícito y conservación de salida parcial/entradas.
Se añaden las pruebas de reglas, API, ledger y mapa de factores de F6.

`scripts/measure_f7_evidence_catalog.py` compara el flujo completo sobre publicaciones
copiadas, adaptando solo el namespace privado del baseline para usar el mismo
verificador SIC F6 en ambas variantes. Tres repeticiones con paridad exacta:

| Variante | Mediana | Pico Python |
| --- | ---: | ---: |
| Original, lectura completa | 0,3647 s | 11,842 MiB |
| Nuevo, frío | 0,3391 s | 11,841 MiB |
| Nuevo, cacheado | 0,0276 s | 0,261 MiB |

El pico mide asignaciones Python, no memoria total del proceso. La mejora principal
corresponde a reutilizar verificación con invalidación, no a cambiar cálculos.
Arquitectura, Ruff, tipos, contratos y congelados se validan separadamente.
