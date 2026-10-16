# Línea base HTTP de ranking y ficha (#157)

Medición del 2026-10-15 sobre el backend `1a1320b`, con cambios locales de esta
entrega. El [JSON íntegro](../api-http-baseline-2026-10-15.json) registra commit,
estado del árbol, SHA-256 del benchmark y fixture, entorno y todas las muestras.
Es una línea base actual, sin cambios de cálculo o rendimiento de producción.

## Reproducción y alcance

Desde la raíz, con las dependencias de desarrollo instaladas:

```powershell
uv run --project backend python scripts/measure_http_api.py --companies 496 --sessions 1250 --repetitions 3 --output docs/api-http-baseline-2026-10-15.json
```

También se puede ejecutar con `.venv/Scripts/python.exe`. Las 496 empresas más
cuatro casos especiales suman **500 empresas**, 1.250 sesiones y **623.755 filas
de precios**, incluido SPY. Semilla 64, fecha financiera 2026-09-29. La fixture
incluye datos ausentes, historia corta y dos clases de un emisor. Toda la base,
pesos y cachés son temporales; no se abre `data/gabi.db` ni se usan fuentes externas.

TestClient recorre HTTP mediante ASGI: rutas, validación, serialización JSON y
respuesta íntegra en memoria. **No incluye TCP ni render del navegador**. El reloj
termina antes de parsear el JSON en el cliente y ejecutar las comprobaciones de
paridad. Las muestras incluyen la sobrecarga de `tracemalloc` y las guardas SQL.
El benchmark no modifica la configuración global ni la aplicación de producción.

Frío significa caché de ranking vacía, sin precalentamiento, no disco frío. La
fixture acaba de escribirse; no se vacía la caché del sistema operativo ni se aísla
la carga de otros procesos. Precalentado significa que se invoca el mismo cálculo
local antes de la petición; su coste se registra aparte y sin `tracemalloc`,
por lo que no se compara directamente con el cálculo instrumentado.

## Resultado observado

Windows 11, Python 3.13.7. Medianas de tres peticiones, salvo los escenarios de
corrección histórica, ejecutados una sola vez. El ranking pide explícitamente
**500 filas**, incluidos ausentes: no es la página habitual de 100 filas.

| Escenario | Tiempo (s) | Pico Python máximo (MiB) | SELECT | Filas del adaptador | Bytes HTTP |
| --- | ---: | ---: | ---: | ---: | ---: |
| Ranking frío, 500 filas | 28,4535 | 29,251 | 104 | 625.552 | 2.526.647 |
| Ranking con caché, 500 filas | 7,4870 | 27,200 | 3 | 17 | 2.526.646 |
| Ranking precalentado, 500 filas | 7,2011 | 27,248 | 3 | 17 | 2.526.646 |
| Filtro Financials, segunda página de 2 filas | 0,1503 | 1,010 | 3 | 17 | 10.353 |
| Ficha fría, 100 barras | 25,0452 | 8,596 | 106 | 625.678 | 13.819 |
| Ficha con ranking cacheado, 100 barras | 0,0982 | 1,158 | 5 | 143 | 13.819 |
| Ranking invalidado por corrección (1 petición) | 30,0593 | 28,588 | 104 | 625.552 | 2.526.739 |
| Ficha tras corrección (1 petición) | 0,0945 | 1,155 | 5 | 143 | 13.804 |
| Ranking corregido con caché vacía (1 petición) | 29,1880 | 28,599 | 104 | 625.552 | 2.526.739 |

El contador del adaptador incluye PRAGMA y filas de metadatos, no solo precios.
El JSON también contiene todos los statements y consultas del adaptador como
recuentos; no guarda el texto SQL ni datos financieros completos. Los bytes
son el cuerpo JSON sin compresión ni cabeceras. El pico Python viene de
`tracemalloc`; los valores RSS/working set del proceso se registran **antes y
después**, no como pico ni memoria atribuible a una única petición. No se
deduce un presupuesto de RAM total de esas asignaciones Python.

La caché evita releer el universo de precios. Sin embargo, devolver las 500 filas
sigue teniendo un coste considerable con instrumentación: el hit no evita
construir, validar y serializar el contrato. La ficha fría calcula primero el
ranking del universo para conservar percentiles y puntuaciones; su fila aislada
no se puntúa de nuevo. Estos datos orientan próximas mediciones, pero no prueban
qué función domina ese coste ni justifican cambiar fórmulas o añadir concurrencia.

## Paridad, efectos y límites

Cada ejecución aborta si no se cumplen:

- Igualdad exacta del payload financiero frío, reutilizado y precalentado,
  exceptuando timestamp de generación, revisión efímera e indicador de hit.
- Orden, métricas, unidades, ausencias y procedencia de las filas filtradas y
  paginadas iguales a las del universo; ficha idéntica a su fila en ese ranking.
- Una corrección del primer precio de T000 en WAL cambia revisión y volatilidad,
  manteniendo la fecha máxima; el resultado coincide con un cálculo nuevo tras
  vaciar caché y la ficha usa la versión corregida.
- Hashes de los archivos de entrada temporales intactos entre GET. La única
  escritura es la corrección explícita de la fixture por una conexión separada.
- Conexiones de la aplicación limitadas a esa base en `mode=ro`; autorización SQL
  que rechaza escrituras y columnas de resultados reservados; archivos Python de
  solo lectura y conexiones IP bloqueadas durante las peticiones. AnyIO se
  inicia antes de la guarda porque Windows utiliza loopback para su socketpair.

`test_http_measurement.py` ejecuta todos los escenarios con seis empresas y
comprueba que las guardas rechazan escrituras, red, ATTACH y lecturas reservadas.
`test_api.py` conserva las pruebas de límites que devuelven `resource_limit` en
vez de truncar métricas, división en lotes, contrato y paridad pre-F2.

## Presupuestos iniciales de seguimiento

Para **esta fixture y este contrato**, mantener como comprobaciones deterministas
el hit de filtros/paginación y la ausencia de carga completa en caché. El valor
observado es 3 SELECT y 17 filas devueltas para ranking cacheado; antes de aumentar
esas lecturas debe justificarse qué dato nuevo se necesita. La ficha cacheada
añade su ventana de 100 precios. Se mantienen los límites de producción de 1.000
símbolos, lotes de 16 y 160.000 filas de precios por lote; estas medidas no los elevan.

Como umbral **manual de investigación**, revisar una duplicación sostenida del
tiempo mediano o del pico Python frente al JSON, con la misma fixture, entorno e
instrumentación y en al menos dos ejecuciones comparables. No es un SLA ni un
test de CI basado en cronómetros. El tamaño del payload y los contadores SQL
permiten distinguir una ampliación del contrato de una regresión de acceso.

No se compara numéricamente con F2/#73/#85: medían casos de uso, otras cargas o
datos locales y no este contrato HTTP de 500 filas con las mismas guardas. Tampoco
se extrapola a 83 GB, a proveedores reales ni a memoria de backtests/worker (#158).
