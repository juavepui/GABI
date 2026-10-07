# Ledger local LIVE_FORWARD (#57)

La [política](POLITICA.md) se fijó en `ecf5085`. `application.administration.periodic.PeriodicTasks.run()` verifica la cadena antes del mantenimiento y, al terminar, añade una decisión con las entradas derivadas completas, fuentes/fechas, universo, ranking, exclusiones, Top-20 propuesto/efectivo, configuración, commit, hashes de código, fingerprint de datos y evidencia/confianza #52. Usa datos de la caché local; no archiva de nuevo los 83 GiB de fuentes crudas.

Los estados son SIGNAL, DEGRADED, NO_SIGNAL y ERROR. Datos de las propuestas o benchmark caducados/futuros/desconocidos, precios inválidos o cambio de sesión durante el cálculo producen estado degradado; fallos del mantenimiento se conservan. Las propuestas quedan visibles para diagnóstico, pero el Top-N efectivo de esas ejecuciones está vacío. La falta de confianza estadística se comunica aparte y no modifica el ranking. El mantenimiento continúa protegiendo los rebalanceos ciegos existentes; el ledger no lee sus resultados.

El resumen de sincronización también queda congelado: fallos parciales en fuentes utilizadas por las candidatas o en composición del universo degradan la decisión aunque la caché previa parezca reciente. Se conservan también los fallos ajenos a esas entradas, por ejemplo SEC de un ETF utilizado solo como benchmark de precios. Fallos sin atribución se tratan conservadoramente. Un error completo se registra y la CLI conserva código de salida 1 para que el Programador de tareas de Windows lo detecte.

Los eventos viven en `data/gabi.db`, tabla `live_ledger`; `data/live_ledger/head.json` es su ancla externa. Triggers impiden UPDATE/DELETE y una cadena SHA-256 cubre todo el payload. El ancla detecta también el borrado del último evento. Un bloqueo de fichero y transacción SQLite serializan escritores; ante cadena/ancla distintas se bloquean nuevas decisiones. No se reclama protección frente a un administrador que reescriba ambos archivos.

```powershell
.venv/Scripts/python.exe -m gabi.live_ledger --verify
.venv/Scripts/python.exe -m gabi_cli periodic --run
```

Una interrupción tras el commit SQLite y antes del ancla requiere revisión explícita. `--recover-anchor "motivo de la revisión"` solo acepta que el ancla anterior sea un prefijo válido de la cadena existente y añade ANCHOR_RECOVERY; no acepta ocultar una cola eliminada. `append_correction(seq, reason, changes)` añade CORRECTION con hash/referencia del original. Ningún evento reemplaza una decisión.

`reproduce_decision(seq)` verifica la huella de entradas y reproduce scores/ranking desde los bloques y pesos congelados, sin usar las fuentes actuales. No reconstruye métricas crudas desde una copia histórica de todos los proveedores. Las huellas de código normalizan LF/CRLF y el registro también conserva versiones de dependencias y entorno.

Desde #88 el informe LIVE_FORWARD vive en `gabi.domain.research.live_performance`. Su fichero
forma parte de los hashes de código del modelo, así que las decisiones registradas a partir de
ese cambio llevan una `model_version` nueva y el informe no las mezcla con las anteriores.

La consulta está en Screener y Research Lab. Permite ver decisiones, comprobar su reproducción, seleccionar una versión y descargar el informe prospectivo. Guardar el informe añade EVALUATION con su huella; visualizar no crea decisiones. RETROSPECTIVE y OOS no se mezclan con LIVE_FORWARD.

El informe sigue la primera decisión de cada sesión de entrada, incluidos fallos y ausencia de señal. Entra en la primera apertura XNYS posterior al timestamp, mantiene una cartera equiponderada por tramos no solapados, calcula la deriva de pesos y aplica 10 pb/lado sobre lo negociado. El último tramo termina en el cierre elegido; SPY se valora en las mismas fechas, con coste inicial. El reporte conserva precios ajustados utilizados, fechas, entidad atribuida cuando existe y huella de resultados. La falta de precio exacto o la identidad desconocida de un ticker reciclado bloquea la acumulación; no se descarta la empresa ni se inventa retorno cero.

Es una **cartera ilustrativa de decisiones registradas**, no operaciones ejecutadas ni el backtest trimestral congelado. Las revisiones posteriores de proveedores pueden cambiar la evaluación y su huella; nunca las entradas de la decisión. No se ha inventado un histórico LIVE_FORWARD para esta entrega: el seguimiento real comienza con las siguientes ejecuciones de mantenimiento.
