# Estado de datos y recuperación operativa (#159–#160)

## Mercado

Ya se distinguían filtros vacíos de caché vacía y la ficha mostraba fechas,
identidad y procedencia. Se conservan. Las brechas eran códigos internos de
aviso, cobertura poco visible y una promesa de consultas «inmediatas».
Ranking y ficha comparten ahora «Estado de los datos», con clasificación y
recuentos del backend: React no deduce frescura ni acreditación financiera.

| Escenario | Presentación y acción |
| --- | --- |
| Caché ausente/insuficiente | Estado explícito y enlace a Administración; consultar no descarga |
| Obsoletos con resultados | Conserva filas y explica avisos por fuente y último precio global |
| Cobertura parcial | Recuentos de precios, fundamentales, SEC y empresas puntuadas; aviso en español |
| Filtros vacíos | Conserva estado/cobertura del universo; mensaje para revisar filtros |
| Error de lectura | Error de API y reintento de lectura, sin POST ni descarga |
| Ficha | Fechas por empresa, identidad y advertencia de que no es histórico point-in-time |

Los recuentos son del universo, no de una página ni empresa. La fecha propia
sigue en la ficha. El aviso de evidencia conserva que la ventaja independiente
frente a SPY no está demostrada. Filtros y ventanas siguen en la URL al recargar.

## Administración

La cola y cancelación cooperativa ya existían. Se añaden explicación de
`worker_interrupted`, distinción entre cancelación solicitada y efectiva y
repetición desde una fila terminal.

Un fallo no previsto (`job_failed`) deja su traza en `jobs/logs/<id>.log`,
dentro de la carpeta de datos (#164). La API solo publica `diagnostic: true` y la
interfaz indica ese fichero; el texto de la excepción no viaja por HTTP. En los
trabajos ciegos, de mantenimiento y Tiingo la traza conserva tipo y pila, pero
omite el mensaje, que podría citar resultados pendientes de #43/#44. Si no se
puede escribir, el trabajo termina igualmente como fallido con `diagnostic: false`.

Nombres en la interfaz: `refresh` es «Actualización completa» (composición del
S&P 500, precios, fundamentales y SEC del universo y los índices de referencia, y
macro FRED; la lanza el Programador a diario) y `data_update` es «Actualizar
datos» (subconjunto elegido de Yahoo y SEC, con descarga forzada opcional).

`POST /api/v1/jobs/{id}/retry` solo acepta `idempotency_key` (8–50 caracteres).
La aplicación relee el origen, admite `refresh`/`quality` fallidos o cancelados,
valida sus parámetros mediante `JobCommand` y vuelve a usar `Jobs.submit`.
No acepta cambios de parámetros. Trabajos activos/completados dan 409; otros
tipos, 403. Investigación, mantenimiento reservado y descargas históricas quedan
fuera, también por URL directa. No se amplían permisos por modo.

Es un **trabajo nuevo**, no reanudación universal; el origen conserva su estado.
El servidor incluye el id del origen en la clave. La UI bloquea doble clic y
guarda la clave pendiente en sessionStorage, con respaldo en memoria. Si pierde
una respuesta, la reutiliza incluso tras recargar. Una respuesta correcta libera
esa clave; una acción posterior es otra solicitud explícita. La clave no contiene
parámetros financieros ni secretos.

El enlace al nuevo intento queda en la URL y apunta a su fila. Interrupciones y
cancelaciones explican que no publicaron resultado; cancelar en curso explica
que espera un punto seguro. Se presentan fase y progreso reales, sin ETA ni
porcentajes inventados. Solo éxitos con referencia permiten abrir resultados.

## Pruebas

Python comprueba duplicados concurrentes, claves por origen, parámetros alterados,
tipos restringidos, cancelación y nuevo intento tras lease interrumpido, conservado
al recrear el cliente. El benchmark usa worker separado y SQLite temporal.
Los nuevos tests de navegador se ejecutan en escritorio y móvil: Mercado usa API
temporal y variantes controladas del contrato; jobs usa estados controlados de UI
para doble clic, respuesta perdida, enlace y recarga, complementados por las
pruebas reales de worker/API en Python.
