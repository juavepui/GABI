# Señales contables de alerta (#293)

Son comprobaciones deterministas sobre datos estructurados de la SEC, sin IA y
sin leer el texto de ningún documento. Están en la versión `tenk-flags-v1`
(`backend/src/gabi/domain/market/tenk_flags.py`). Cada señal indica su regla,
su umbral, los valores que usó y la presentación SEC de la que salen (accession
y fecha). Una señal pide revisar la empresa; nunca dice que haya que vender.

| Señal | Regla | Umbral |
| --- | --- | --- |
| Cuentas anuales corregidas | 10-K/A presentado en los 365 días anteriores | — |
| Informe anual tarde | NT 10-K presentado en los 365 días anteriores | — |
| Cambio de auditor | 8-K con Item 4.01 en los 365 días anteriores (#292) | — |
| Cuentas no fiables | 8-K con Item 4.02 en los 365 días anteriores (#292) | — |
| Cuentas a cobrar | crecimiento de cuentas a cobrar − crecimiento de ventas, último ejercicio | > 15 puntos |
| Devengos | (beneficio neto − flujo de caja operativo) / activos totales medios | > 0,10 |
| Dilución | crecimiento de las acciones diluidas medias, último ejercicio | > 5 % |

## Reglas comunes

- **Solo lo presentado hasta la fecha de análisis (point-in-time).**
  - Las cifras se leen de los hechos con `filed_date ≤ fecha`.
  - Para cada cierre se usa el último 10-K o 10-K/A presentado. Un 10-K posterior que reexpresa un año solo cuenta a partir de su fecha de presentación.
  - Las presentaciones se filtran por su fecha.
- **Ejercicios comparables.**
  - Las cifras de flujos necesitan un periodo de entre 340 y 380 días.
  - Los saldos son los del cierre del 10-K.
  - Los dos ejercicios comparados deben estar separados por un año.
- **Ausencia.** Sin el dato necesario, la señal sale «no evaluable» con su motivo, nunca «sin alerta». Las comprobaciones de 10-K/A y NT 10-K tampoco se evalúan si el índice guardado es anterior a #293. Para eso, `sec_filing_index` registra qué formularios buscó cada captura.

## Datos

- **Índice de presentaciones.** Se guarda en `sec_current_reports`, junto a los 8-K de #292, con los formularios 10-K/A y NT 10-K. Se guarda en la misma sincronización SEC, sin peticiones extra.
- **Cuentas a cobrar.** La etiqueta `AccountsReceivableNetCurrent` se añade a `FACT_TAGS`. Como pasa al añadir cualquier etiqueta, cada emisor guardado se reprocesa una vez en la siguiente sincronización.
- **Resto de cifras.** Ventas, beneficio, flujo de caja operativo, activos y acciones diluidas son las etiquetas que ya guardaban el Composite y el checklist.

## Dónde se ve

- **Ficha:** «Señales contables de alerta (10-K y 8-K)». Se consulta con `GET /api/v1/companies/{symbol}/accounting-flags`, que solo lee.
- **Ideas abiertas (#247):**
  - Una señal en alerta, presentada después de publicar la idea, crea una alerta `contable` de revisión (`idea-alerts-v3`).
  - El cambio de auditor y las cuentas no fiables no se repiten aquí, porque ya los avisa la alerta `8k` de #292.
