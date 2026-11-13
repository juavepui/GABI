# F7.4: contexto y sincronización FRED

Entrega para #90/#91. El refresco de macro comparte
`application/administration/fred.py` entre la fachada publicada y la composición
de CLI/worker. Settings, clave, repositorio, fuente, checkpoint, intento, reintento,
clasificador, reloj y progreso son entradas explícitas. No modifica configuración
global por operación. El bootstrap construye los adaptadores sin abrir conexiones,
leer claves ni descargar datos.

## Reglas conservadas

`domain/market/fred.py` conserva exactamente las nueve series, etiquetas, ayudas,
unidades y transformaciones FRED (`lin`/`pc1`). Los metadatos compartidos son
inmutables; la fachada mantiene su diccionario mutable de compatibilidad. El
parser conserva orden y valores retirados (`.`/null). La comparación de claves,
NaN y revisiones está en `domain/market/observations.py`; `sync_state` conserva
los nombres públicos delegados para los consumidores pendientes.

El TTL vence estrictamente después de 24 horas; un checkpoint fallido fuerza
reintento. La primera auditoría y las siguientes, a los 30 días o por acción
explícita completa, empiezan en `1776-07-04`. La ventana incremental solapa
400 días. Un refresco sin cambios renueva `macro_meta`; un valor retirado se
escribe como NULL. El watermark usa solo fechas con valor y no retrocede. Una
respuesta vacía/duplicada o un fallo conserva el último éxito y registra el fallo.
El timestamp de auditoría procede del reloj de la operación.

`SqliteFred` abre y cierra una conexión por lectura/escritura. No mantiene una
conexión durante red/reintentos. Las lecturas son de solo lectura y no crean DB
ni tablas cuando faltan. Metadatos y fallos se consultan por las series solicitadas;
la historia contiene solo fecha/valor de una serie. Las escrituras usan las tablas
existentes y transacciones cortas. Los errores mantienen la retención de 90 días.

La API conserva `MacroQueries` y su consulta indexada de último valor no nulo
y valor anterior a 90 días. Ya obtiene metadatos del dominio, retirando el puente
`infrastructure/legacy/macro.py`. El contrato sigue convirtiendo WALCL de millones
a USD y publicando las unidades de cambios. La fachada `get_snapshot` mantiene
su comportamiento histórico, incluida la última observación NULL; no sustituye
el contrato HTTP por esa interpretación. GET no descarga ni escribe.

## Límites e invalidación

- Hasta 100 series por lectura de metadatos/fallos, 100.000 observaciones por
  serie almacenada/escritura y por respuesta de sincronización. El lector pide
  límite + 1 y rechaza exceso; no trunca una historia silenciosamente.
- Fuente: timeout 20 s, streaming en bloques de 64 KiB, máximo 32 MiB decodificados.
  Rechaza respuestas que requieren paginación antes de avanzar checkpoints.
- Clave local `fred_api_key.txt`, máximo 4096 bytes, misma prioridad histórica
  sin variable de entorno alternativa. Las excepciones HTTP/red no incluyen la clave.
- Checkpoints/eventos usan `OperationSyncEvents` y su límite de 2 MiB por estado.
  El puente de reintentos conserva tres intentos y pacing/backoff compartidos.
- La revisión de la caché de mercado sigue invalidándose por commit SQLite/WAL;
  una revisión histórica invalida aunque la fecha final no cambie. El TTL del
  refresco no sustituye la procedencia ni los checkpoints.

## Evidencia y medida

Fixture independiente `backend/tests/fixtures/fred_migration.json`, capturada del
commit `88880ecca34a20c519b516145055f097ca37d627` antes de extraer el código. No
necesita historia Git en CI. Las pruebas comparan resultados y contenido completo
de `macro_series`, `macro_meta`, `sync_checkpoints`, `sync_events` y `update_errors`
con relojes fijos. Incluyen cambios, ausencias, retirada, duplicados, respuesta
vacía, fallo, TTL/auditoría, límites, cierre HTTP, claves, fachada, API y callbacks
de composición. Solo fixtures, DB temporales y red simulada.

`python scripts/measure_f7_fred.py`: nueve series sintéticas diarias 1990–2024,
111.771 filas, 2.447.811 bytes de payload lógico; cuatro DB nuevas por variante,
primera medición y mediana de tres repeticiones posteriores. Sin descargas.

| Flujo | Variante | Primera (s) | Mediana posterior (s) | Pico Python (MiB) | Conexiones | SELECT |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Refresco inicial | Original | 3,8957 | 3,9142 | 3,3376 | 47 | 29 |
| Refresco inicial | Migrada | 3,6091 | 3,6235 | 3,2928 | 43 | 25 |
| Caché vigente | Original | 0,001788 | 0,001266 | 0,003629 | 2 | 2 |
| Caché vigente | Migrada | 0,001267 | 0,001241 | 0,004623 | 2 | 2 |

Los SELECT incluyen prepares fallidos por tabla ausente (uno en la variante
migrada inicial). Filas, metadatos, eventos y checkpoints coinciden en las cuatro
repeticiones. El pico es de asignaciones Python, no RSS; la primera medición no
acredita caché fría del sistema operativo. La caché vigente usa ligeramente más
memoria Python. No se atribuye una mejora general de rendimiento.

## Deuda que continúa

El inventario conserva 76 módulos planos: `macro` sigue como fachada de IO para
`history_refresh`, `data_quality`, `screener` y consumidores publicados. Esos
flujos deben migrar sus propios accesos antes de retirarla. El pacing/reintento
permanece en el puente explícito `source_errors`; su almacenamiento y política
global compartida requieren la entrega de fuentes restante. No se han añadido
excepciones; se retira la dependencia pandas de `sync_state`.
Los 18 motores/configuración congelados y sus sellos permanecen intactos.
Esta entrega no completa la aceptación global de #90/#91 ni aporta evidencia #60.
