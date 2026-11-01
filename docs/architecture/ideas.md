# Historial de ideas (#247)

Al publicar una ficha de inversión (#246) se crea una **idea**. Una nota editable
no equivale a un historial, así que lo que pasa después se registra como eventos
que solo se añaden.

## Eventos

`domain/portfolio/ideas.py`, versión `ideas-v1`.

| Evento | Cuándo | Contenido |
|---|---|---|
| `publicada` | Al publicar la ficha, una sola vez por ficha (idempotente) | Ficha, símbolo, huella del snapshot, fecha de revisión, importe y costes de ida y vuelta |
| `revisada` | Cuando el inversor revisa la idea | Texto |
| `retirada` | Al descartar una ficha publicada o retirarla a mano | Motivo |
| `cerrada` | Al cerrar la idea | Resultado de la tesis (acertada, parcial o fallida), causa y si llegó a invertirse |
| `corregida` | En cualquier momento, también después del cierre | Evento que corrige y texto. El original no se toca |

- **Cadena de huellas:** cada evento lleva la SHA-256 del anterior. `chain_ok`
  delata cualquier reescritura y la pantalla la marca como «Historial alterado».
- **Almacenamiento:** la tabla `idea_events` solo admite inserciones. Una
  inserción concurrente con la misma secuencia falla y devuelve un conflicto (409).
- **Después de cerrar o retirar** solo se admiten correcciones.
- **Notas privadas:** viven en `idea_notes`. Se editan y se borran sin afectar a
  ningún evento.

## Evaluación

`application/portfolio/ideas.py` lee solo la caché local de precios: cierre
ajustado del valor, SPY y USDEUR=X. Nada se descarga.

- **Periodo:** desde el día en que se **registró** la publicación (nunca antes:
  nada se registra retrospectivamente como prospectivo) hasta el cierre, la
  retirada u hoy.
- **Cálculo:** rentabilidad total en EUR neta de los costes de ida y vuelta de
  la ficha, frente al S&P 500 en EUR en las mismas sesiones. Se dan la
  diferencia, la máxima caída de cada uno y el plazo.
- **Sin precios:** si falta una serie (por ejemplo, un ticker que cambió), la
  idea queda `insufficient_prices` y se nombra la serie que falta, sin estimar.
- **Resumen:** cuenta **todas** las ideas, también las abiertas, cerradas,
  retiradas, perdedoras y no invertidas. Da cuántas superan al índice, la
  diferencia mediana y media, y los aciertos de tesis de las cerradas.
- **Datos tardíos o corregidos:** cambian la evaluación cuando llegan a la
  caché, pero nunca los eventos.

## API y pantalla

| Método | Ruta | Uso |
|---|---|---|
| GET | `/api/v1/portfolio/ideas` | Todas las ideas, con su estado, evaluación y resumen. Sin efectos. |
| GET | `/api/v1/portfolio/ideas/{id}` | Eventos y notas de una idea. |
| POST | `/api/v1/portfolio/ideas/{id}/events` | Revisión, retirada, cierre o corrección. La publicación solo la registra la ficha. |
| POST | `/api/v1/portfolio/ideas/{id}/notes`, `…/notes/{nota}/save`, `…/notes/{nota}/delete` | Notas privadas. |

La página es **Cartera → Historial de ideas** (`/cartera/ideas`).

## Alertas

**Job explícito e idempotente** `idea_alerts`:
- se lanza con «Buscar alertas» en el Historial de ideas;
- usa `domain/portfolio/idea_alerts.py` (`idea-alerts-v1`) y
  `application/portfolio/idea_alerts.py`;
- en el worker, lo compone `infrastructure/legacy/idea_alerts.py`.

Para cada idea **abierta** lee solo datos locales: su ficha publicada, la
checklist de la empresa, los últimos 10-K/10-Q, las sorpresas de resultados, la
revisión del consenso a 90 días, el resumen de insiders y su evaluación. No
descarga nada: para traer datos nuevos están los jobs de sincronización ya
existentes.

| Alerta | Cuándo |
|---|---|
| `invalidacion` | La condición registrada (métrica de la checklist, operador y umbral) se cumple en tantos ejercicios fiscales distintos seguidos como pide su persistencia. |
| `revision_dato` | El mismo ejercicio tiene otro valor (un dato reexpresado o corregido). No es un deterioro por sí solo. |
| `ausencia` | La métrica no tiene valor. Falta el dato, no es un deterioro. |
| `no_evaluable` | La condición nombra una métrica que la checklist no calcula. Hay que revisarla a mano. |
| `revision_vencida` | Llega la fecha de revisión de la ficha o de una condición. |
| `filing` | Hay un 10-K o 10-Q presentado después de la publicación. |
| `resultados` | Sorpresa negativa en resultados posteriores a la publicación. |
| `estimaciones` | El consenso de BPA baja al menos un 5 % en 90 días. |
| `insiders` | Al menos dos insiders venden en neto en seis meses. |
| `tendencia` | La idea va 10 puntos por detrás del índice o ha caído un 20 % desde su máximo. |

- **Persistencia:** el job guarda las observaciones de cada condición
  (`idea_observations`), y con ellas cuenta los ejercicios seguidos y distingue
  una reexpresión de un deterioro.
- **Idempotencia:** cada alerta tiene una clave estable, así que repetir el job
  con los mismos datos no añade nada.
- **Alertas pendientes:** son las detectadas después de la última revisión,
  cierre o retirada del inversor. Atenderlas es añadir una revisión.
- **Alcance:** las ideas cerradas o retiradas dejan de vigilarse, pero se siguen
  evaluando. **Ninguna alerta opera**: solo piden revisar.
