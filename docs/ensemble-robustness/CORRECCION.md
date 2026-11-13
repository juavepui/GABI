# Corrección de implementación: emisores con dos símbolos en una fecha

La primera ejecución del motor (`4813b4e`) se detuvo en la validación de
entrada, **antes de reproducir los bloques y antes de calcular cualquier
métrica**. No se produjo ningún resultado, parcial ni completo.

## Causa

El preregistro (`9f6d5e8`, huella `8609a077…`) fija `identity: entity_id`.
Supone, sin decirlo, un símbolo por emisor y fecha. `scores.csv` de #60
contiene 94 filas, en 42 fechas, de seis emisores con dos símbolos en la
misma fecha:

- dos clases de acciones: GOOG/GOOGL, DISCA/DISCK y NWSA/NWS;
- un cambio de ticker con el mismo CIK: KORS/CPRI y CCE/CCEP.

#60 trató cada símbolo como una fila elegible y seleccionable. El motor
rechazaba ese caso en lugar de aplicarle una regla.

## Regla aplicada

Esta es la extensión más fiel a `identity: entity_id` y a 20 plazas. Se fijó
sin ver ningún resultado.

- **Universo y selección**: idénticos a #60. No se elimina ninguna fila. La
  selección recorre símbolos con el orden, el tope por división y el
  desempate declarados.
- **Posiciones**: cada Top-20 es un **multiconjunto de `entity_id`**. Dos
  clases del mismo emisor ocupan dos plazas, y un cambio de ticker del mismo
  emisor no cuenta como rotación. Rotación, persistencia, solapamiento y
  dominancia usan intersecciones y uniones de multiconjuntos sobre 20 plazas.
- **Autocorrelación descriptiva**: se excluyen los emisores con dos filas en
  cualquiera de las dos fechas, y su número se publica.

No cambian componentes, pesos, universo, ruido, semillas, inferencia ni
umbrales de decisión. El fichero de selecciones publica, por emisor, el
número de plazas que ocupa.
