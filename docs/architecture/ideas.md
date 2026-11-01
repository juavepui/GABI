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

## Pendiente (segunda parte)

- **Alertas:** un job explícito e idempotente que evalúa las condiciones de
  invalidación registradas con los datos disponibles (resultados, filings,
  insiders, revisiones y tendencia). Distingue deterioro, revisión del dato y
  ausencia, y solo pide revisión: nunca opera.
