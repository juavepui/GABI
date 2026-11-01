# Ficha de inversión versionada (#246)

La selección cuantitativa solo prioriza qué analizar; la decisión es del
inversor y la ficha la deja escrita. Extiende las tesis del diario (#186) con una
estructura completa y versionada. Es la primera entrega de #246: la estructura.
El benchmark en EUR, los costes, la aportación al riesgo de cartera y las 30
fichas de validación van en la segunda.

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
