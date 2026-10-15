# Worker y API concurrente (#158)

El [informe del 2026-10-15](../worker-api-baseline-2026-10-15.json) mide una API
TestClient/ASGI y un worker en **otro proceso**, con SQLite temporal en WAL.
No abre `data/`, descarga fuentes ni ejecuta investigación o reservas #43/#44.

```powershell
uv run --project backend python scripts/measure_worker_api.py --companies 496 --sessions 320 --output docs/worker-api-baseline-2026-10-15.json
```

Semilla 64, 500 empresas incluidos cuatro casos especiales, 320 sesiones y
159.685 precios. Una muestra por combinación: refresco/auditoría, sin/con
consultas concurrentes. Cola y artefactos son reales. El refresco usa
`universe_data` y `SqliteCacheWrites` con proveedor determinista: 501 cierres
(incluye SPY), 500 fundamentales y demora simulada de 5 ms por lote. Excluye
descubrimiento del universo, macro, SEC y latencias de Yahoo: mide el tramo de
caché de mercado, no el refresco completo. La auditoría usa `quality_snapshot`.

| Operación | Ejecución sin/con lectores (s) | Pico RSS del worker sin/con (MiB) | Pico Python sin/con (MiB) |
| --- | ---: | ---: | ---: |
| Refresco de caché | 6,2089 / 7,1066 | 177,14 / 178,05 | 3,005 / 3,334 |
| Auditoría de cobertura | 0,0297 / 0,0226 | 174,27 / 174,68 | 0,326 / 0,326 |

Windows 11/Python 3.13.7, base `5467954` con el script de esta entrega. Son
muestras individuales instrumentadas, **no medianas ni evidencia de mejora**.
Ejecución excluye arranque del proceso y sincronización; el JSON también guarda
el tiempo del worker con coordinación. RSS/working set se muestrea cada 5 ms e
incluye imports y memoria nativa: puede perder el máximo instantáneo.
`tracemalloc` mide asignaciones Python por separado. No incluye TCP/render.

El refresco dedicó 0,1491/0,1479 s al proveedor y 6,0595/6,9583 s a persistir.
Hubo 9.550 statements (8 SELECT), incluidos esquema y transacciones por escritura.
Esto señala la persistencia para perfilar, sin autorizar cambios de transacciones
o procedencia sin pruebas. La auditoría usó 18 SELECT incluida la cola. Los
artefactos midieron 132 bytes (refresco) y 169 bytes (auditoría).

## Concurrencia y comprobaciones

Antes de liberar al ejecutor, el padre comprueba que el job está en curso y sin
resultado publicado. Después realiza tres lecturas de cola y tres de ranking
de 10 filas. No todas siguen solapándose con el cálculo: la auditoría puede
acabar antes de la primera lectura de ranking. El JSON guarda respuesta,
duración, bytes y contadores del adaptador de **mercado**, no de la cola.

Durante el refresco, la lista de trabajos tardó 0,0041–0,0047 s. El ranking dio
un hit de 0,0832 s y dos `409 data_changed` tras 6,0669 y 5,3006 s: hubo commits
entre el inicio y la comprobación de revisión. No se publicó esa respuesta y el
último cálculo, sin cambios concurrentes, fue correcto. Durante la auditoría los
rankings dieron 200, tardaron 0,0760–0,0795 s y leyeron 17 filas del adaptador.

La ejecución exige igualdad exacta entre modos del resultado íntegro, las filas
de precios/fundamentales/SEC y las primeras candidatas con todas sus métricas,
fechas, unidades y procedencia. La auditoría no puede cambiar esas tablas.
Cada artefacto debe tener el SHA-256 publicado y no dejar temporales. Se prohíben
conexiones IP en el worker y se simulan los puertos de proveedor.
`test_worker_measurement.py` repite el recorrido con seis empresas, sin umbrales
de tiempo. Las pruebas de API/worker comprueban aparte GET sin efectos y que
fallos/cancelaciones no publican resultados parciales.

## Presupuesto de seguimiento

Mantener **un worker** y los límites actuales de lectura. Registrar los 409
separados de latencias de respuestas correctas. Comparar futuras optimizaciones
con la misma fixture y ventanas, con y sin lectores. Investigar duplicaciones
sostenidas de tiempo o memoria en dos ejecuciones comparables; no fallar CI por
un cronómetro. Contadores, volumen de escrituras y artefactos son los primeros
controles deterministas. No extrapolar a 83 GB, backtests ni proveedores reales.
Esta entrega publica una referencia, sin cambiar concurrencia o cálculos.
