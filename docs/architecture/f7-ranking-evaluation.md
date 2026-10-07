# F7.4: seguimiento de rankings y resultados posteriores

Se retira `gabi/evaluation.py` y el puente `legacy/snapshots.py`. No quedan
consumidores de producción del nombre plano ni motores congelados que lo importen.
El inventario pasa de 80 a 79 módulos; las excepciones no se amplían.

## Flujo compartido

`application/market/snapshot_math.py` recibe lector y fecha explícitos. Reúne los
precios de inicio/fin antes de llamar a `domain/portfolio/evaluation.py`, que solo
recibe valores y series en memoria. Conserva la media equiponderada, SPY, costes
de ida y vuelta, ausencias, estado obsoleto, deduplicación en horizontes y curvas
base 100. Un horizonte pendiente no consulta precios.

API de rankings y worker de resultados históricos usan las mismas funciones.
Los lectores F5/F6 mantienen ventanas de siete días, el corte observado y los
límites existentes. No hay nuevas descargas, backtests ni lecturas de reservas.
La política de caché permanece: cada consulta lee SQLite; no se añade otra caché.
La extracción no cambia el camino de datos, por lo que no se atribuye una mejora
de rendimiento.

`SqliteSignals` conserva tablas, selección de candidatas y metadatos. Recibe
directorio y reloj por instancia; el reloj predeterminado conserva la zona de
Madrid y precisión de segundos. Sus lecturas de esquemas históricos siguen
sin DDL ni backfill: nombres/confianza/sector ausentes se presentan mediante
proyección. Guardar o renombrar son acciones explícitas que adaptan el esquema.
El antiguo listado que escribía durante una lectura desaparece. El contrato HTTP
y el límite F5 de 50 snapshots/100 candidatas permanecen.

## Evidencia

`fixtures/evaluation_migration.json` recoge seis casos del código previo, con
commit y SHA-256 normalizado a LF: completos, ausentes, ceros, duplicados,
obsolescencia y horizonte pendiente. Se comparan progreso, horizonte y curva;
solo los flotantes usan tolerancia de redondeo (`1e-12` relativo, `1e-14` absoluto).
Pruebas adicionales comprueban pureza, reloj obligatorio, conservación de entradas,
directorios/relojes independientes y bytes SQLite intactos durante consultas.
Las pruebas anteriores se componen sobre repositorios explícitos y un lector
completo de referencia aislado, para seguir contrastando las ventanas SQL.

Validación: 48 pruebas de evaluación, API de seguimiento, worker histórico,
señales y migraciones; arquitectura, Ruff, tipos, contrato y motores congelados. Los
artefactos publicados no se modifican.
