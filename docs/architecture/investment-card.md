# Ficha de inversión versionada (#246)

La selección cuantitativa solo prioriza qué analizar; la decisión es del
inversor y la ficha la deja escrita. Extiende las tesis del diario (#186) con una
estructura completa y versionada. Se entregó en dos partes: primero la estructura (#277) y después el contexto de
decisión y la validación.

## Contenido

`domain/portfolio/investment_card.py`, versión `investment-card-v1`.

| Bloque | Contenido |
|---|---|
| Tesis | Un máximo de tres líneas. |
| Expectativa discrepante | Qué descuenta el precio y por qué discrepa el inversor. |
| Valoración | Escenarios pesimista, base y optimista, cada uno con precio y supuestos, y bear ≤ base ≤ bull. Texto de sensibilidad. |
| Catalizadores | Descripción y horizonte (fecha). |
| Riesgos | Lista. |
| Invalidación | Condiciones medibles: métrica, fuente, operador, umbral, persistencia (periodos seguidos) y fecha de revisión. |
| Confianza subjetiva | Baja, media o alta. **No es una probabilidad**. |
| Revisión | Fecha prevista, futura al publicar. |
| Importe previsto | Euros de la posición. Obligatorio para publicar, porque con él se calculan costes y concentración. |

## Estados

`incompleta` → `analizada` → `publicada`; desde cualquiera de ellos, `descartada`.

- **`analizada`** exige la tesis y los tres precios de escenario.
- **`publicada`** exige la ficha completa. Si falta algo, la respuesta nombra
  cada pieza que falta, sin rellenarla.
- **`descartada`** exige un motivo. Es una conclusión válida: puede no haber una
  oportunidad suficientemente defendible.
- **Versiones:** una versión publicada o descartada no se edita. Para cambiarla
  se abre una versión nueva (v2, v3…), y solo puede haber una abierta por
  empresa. Editar una ficha `analizada` la devuelve a `incompleta`.

## Datos capturados al publicar

`application/portfolio/investment_cards.py` lee solo la caché local y no
descarga nada. Guarda en `snapshot_json`, con su SHA-256 en `snapshot_sha256`:

- el modelo vigente, el instrumento (símbolo y USD) y el emisor (entidad, CIK y
  fuente de identidad);
- el precio de la caché con su fecha, y el score del ranking congelado;
- las métricas de la checklist, cada una con su valor, unidad, fuente y periodo,
  más la fecha de la checklist, el cierre fiscal, la versión de umbrales, el DCF
  inverso y los múltiplos históricos;
- la evidencia del modelo, con tres conceptos separados: cobertura del dato,
  evidencia estadística y nivel de confianza del modelo. La confianza subjetiva
  del inversor va aparte, en el contenido;
- `absent`: todo lo que faltaba (precio, identidad, checklist, evidencia o
  métricas sin valor), nombrado, nunca rellenado.

Los movimientos de cada escenario se calculan sobre el precio publicado.

Además se guardan los comparables sectoriales de la checklist (medianas del
sector en el universo actual) y el **contexto de decisión** (`snapshot.decision`),
calculado con funciones puras del dominio:

- **Costes** (`position_costs`): comprar y después vender el importe previsto con
  el bróker del perfil del inversor (#244), es decir, comisión fija, comisión
  porcentual y cambio de divisa. Se dan en euros y como porcentaje del importe.
- **Riesgo de cartera** (`concentration`): peso del emisor y del sector ahora y
  tras añadir la posición, frente a los límites de la política vigente (#248).
  Indica si los supera; no bloquea ni decide.
- **Alternativa pasiva** (`passive_comparison`): el escenario base anualizado
  hasta la fecha de revisión y neto de costes de ida y vuelta, junto a la
  rentabilidad anual pasada del S&P 500 en EUR con las aportaciones del propio
  inversor (TWR del benchmark de #244). **Ninguna de las dos cifras es una
  previsión**, y la ficha lo dice.

Si falta el perfil, la cartera, el benchmark o los comparables, el dato queda
vacío y se nombra en `absent`.

## Validación

`tests/test_investment_cards_validation.py` publica **30 fichas de fixtures**,
que combinan qué datos existen y cuáles faltan, de modo que cada dato aparece
tanto presente como ausente. Para cada ficha comprueba:
- que la huella reproduce el snapshot y que los mismos datos dan la misma huella;
- que cada métrica nombra una fuente y un periodo conocidos;
- que cada dato ausente queda vacío y nombrado, sin inventarse;
- que los movimientos de los escenarios y la comparación con la alternativa
  pasiva se recalculan exactamente desde el snapshot.

## API y pantalla

| Método | Ruta | Uso |
|---|---|---|
| GET | `/api/v1/portfolio/cards?symbol=` | Versiones, de la más reciente a la más antigua. Sin efectos. |
| GET | `/api/v1/portfolio/cards/{id}` | Una versión. |
| POST | `/api/v1/portfolio/cards` | Versión nueva, `incompleta`. |
| POST | `/api/v1/portfolio/cards/{id}/save` | Guarda el borrador. |
| POST | `/api/v1/portfolio/cards/{id}/state` | Destino `analizada`, `publicada` o `descartada` (con motivo). |

La sección «Ficha de inversión» de la página de empresa
(`features/market/investment-card.tsx`) muestra la última versión:
- si está abierta, el formulario y lo que falta para publicar;
- si está publicada, la lectura, con la cobertura, la evidencia y la confianza
  separadas y la huella de los datos capturados;
- si está descartada, su motivo.

Debajo aparece el historial de versiones. Todo se guarda en la tabla
`investment_cards` de `gabi.db`.
