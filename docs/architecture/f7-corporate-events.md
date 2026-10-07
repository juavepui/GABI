# F7.4: calendario corporativo y sorpresas de resultados

Se elimina `gabi/events_calendar.py` después de migrar su único consumidor plano,
Screener, a `domain/market/events.py`. Inventario: 78 módulos; se retiran el módulo
y el import de Screener del baseline, sin excepciones nuevas.

## Flujos

El dominio conserva fechas Yahoo en UTC, ventanas estimadas/confirmadas,
dividendos, días hasta el evento, resultados ya reportados y reacción en porcentaje.
El día de corte es obligatorio. Calendarios agregados reciben los fundamentales
ya seleccionados en memoria; no consultan SQLite ni red. Ranking y ficha usan
el mismo parser y los resultados de EPS siguen sin incorporarse al score.

`application/market/earnings_sync.py` procesa intentos por símbolo, lee precios
solo cuando hay EPS reportado y guarda explícitamente. Recibe fuentes, repositorio,
clasificador de errores, progreso y día. El worker pasa su reloj de día. El puente
Yahoo conserva normalización de ticker, hasta seis descargas paralelas por defecto
y mensajes de error anteriores; no modifica configuración global.

`SqliteEarnings` recibe directorio/reloj de registro. Conserva clave
`symbol/earnings_date`, INSERT OR REPLACE, fuente, unidades y timestamp UTC.
Guardar vacío no crea archivos. La consulta pública sigue usando el repositorio
F5 de solo lectura y su límite de 200 sorpresas; desaparece el getter que creaba
tablas durante una lectura. El contrato HTTP no cambia.

La reacción usa el último precio anterior y primero en/después de cada fecha,
incluidos cero/null y huecos arbitrariamente largos, como antes. Una consulta
SQLite por símbolo obtiene ambos vecinos de hasta 200 fechas, en lugar de cargar
toda la serie. No introduce una tolerancia de siete días ni omite nulos para
buscar otro cierre. El ledger captura la ruta de dominio de eventos en futuras
versiones; los registros y motores congelados anteriores permanecen intactos.

## Evidencia y medición

`fixtures/events_migration.json` conserva el original `486942a`, con SHA normalizado
a LF: eventos confirmados/estimados/inválidos/ausentes, EPS nulo/cero/futuro y
reacciones sin precio, nulas o con cero. Pruebas adicionales verifican clock,
idempotencia, aislamiento de directorios, ausencia de escritura al consultar,
clasificación/progreso y paridad de lectura acotada frente a la serie completa.

`scripts/measure_f7_earnings_sync.py` compara el flujo completo, incluida
persistencia, sobre dos SQLite sintéticos en WAL. Adapta únicamente namespaces
privados del baseline para fuentes y clocks, sin modificar globals operativos.
20 símbolos, 3.803 sesiones por símbolo, 20 reportes, tres repeticiones; todas las
columnas persistidas coinciden exactamente:

| Variante | Mediana | Pico Python |
| --- | ---: | ---: |
| Original con serie completa | 7,4526 s | 1,959 MiB |
| Nuevo con precios vecinos | 1,6429 s | 0,123 MiB |

La fuente de EPS es sintética: la medición no incluye latencia de Yahoo. El pico
mide asignaciones Python, no memoria total. Arquitectura, Ruff, tipos/contratos
y congelados se comprueban aparte de estas referencias.
