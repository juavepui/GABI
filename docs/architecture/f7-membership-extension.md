# F7.4: reproducción de cambios revisados de índice

`domain/research/membership.py` valida y reproduce el ledger recibido sobre
una historia explícita. El día de revisión es obligatorio y el dominio no lee
archivos ni obtiene la fecha actual. La fachada conserva su ruta al recurso
publicado y sus firmas; pasa fecha local como el original.

Se conservan normalización punto/guion, hash del conjunto de ancla, orden estable,
cambios simultáneos, intervalos, fuentes HTTPS, altas/bajas, reconciliación del
endpoint y errores exactos. Las filas originales y duplicidades anteriores al
ancla permanecen; repetir la extensión es idempotente. Historias con otra ancla
se devuelven intactas. No se modifica el recurso `sp500_extension.json`.

Diez casos capturados del original cubren reproducción y conflictos; se comprueban
entradas sin mutación, fecha obligatoria, idempotencia y ejecución sin archivos.
También se mantienen las pruebas del recorrido completo de membresía y refresh.
Esta entrega no cambia acceso a datos ni caché: los tres consumidores legacy
conservan la fachada hasta migrar sus lectores. No se atribuye rendimiento.
