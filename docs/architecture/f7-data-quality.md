# F7.4: reglas y casos de uso de calidad de datos

`domain/market/data_quality.py` reúne edades de fuentes, cobertura/frescura por
universo, procedencia por símbolo, cobertura por bloque, avisos y candidatas con
baja confianza. Recibe metadatos en memoria, fecha explícita y configuración de
TTL. Conserva ausencias, fechas, unidades, límites estructurales y los avisos.
Las métricas oficiales se capturan en una tupla; la fachada puede pasar las
métricas legacy cuando sus consumidores las adapten.

`application/administration/data_quality.py` recoge metadatos mediante callbacks
específicos (`QualityReaders`) y aplica un reloj por operación. Las fechas de
sector usan UTC: día actual y referencia de un año antes, o `as_of` explícito.
Un universo vacío no invoca lectores. El worker comparte estos casos de uso y
recibe reloj por instancia; los avisos de API/backtests usan dominio directamente.

`gabi/data_quality.py` conserva compatibilidad y composición de los lectores
antiguos. Sus operaciones locales de CIK y fingerprint de caché siguen pendientes
de trasladar junto a los repositorios compartidos. El job de auditoría sigue
verificando que su directorio coincida con el bootstrap de compatibilidad; no se
mutan settings por trabajo. No se presenta esa infraestructura pendiente como
migrada ni se eliminan excepciones que aún usa. Permanecen 79 módulos planos.

## Evidencia

`fixtures/data_quality_migration.json` captura el original `486942a`, con SHA
normalizado a LF, sobre fuentes sintéticas de fecha fija: universo con fuentes
frescas, caducadas, futuras y ausentes; procedencia de tres símbolos; diagnóstico
de ranking y ranking vacío. Conserva orden/mensajes/fechas y normaliza únicamente
NaN a null al comparar salidas serializadas. El código base de captura utiliza
reloj y lectores en su propio namespace, sin consultar SQLite ni fuentes.

Se conservan las 32 pruebas del módulo anterior. Las adicionales comprueban
referencias completas, inputs sin mutación, ausencia de SQLite/red en dominio,
lectores sin llamadas para un universo vacío, reloj del worker y fechas UTC.
Arquitectura, Ruff, tipos/contratos y congelados se validan aparte. No se añade
caché ni se cambia el camino de datos: no se atribuye una mejora de rendimiento.
