# Mi cartera completa (#294)

«Mi cartera» (#181) admite tres tipos de movimiento (`kind`):

| Tipo | Campos | Efecto |
| --- | --- | --- |
| `buy` (compra) | acciones, precio por acción, comisión | entra dinero (+ coste con comisión) |
| `sell` (venta) | acciones, precio por acción, comisión | sale dinero (− lo cobrado menos la comisión) |
| `dividend` (dividendo) | `price` = importe bruto, `withholding` = retención | sale dinero (− importe neto) |

## Reglas

- **No se vende más de lo que se tenía.** Nunca se vende más de lo que se tenía ese día ni se apunta un dividendo sin acciones (`holdings.check_sequence`). En un mismo día cuentan primero las compras.
  - Lo mismo vale al editar.
  - No se puede borrar una compra si una venta o un dividendo posteriores se quedarían sin acciones.
- **Coste de lo vendido: coste medio.** Una venta saca del coste la parte vendida. La ganancia realizada es lo cobrado menos ese coste, en euros.
- **Tabla de antes de #294:** gana las columnas `kind` y `withholding` en su primera escritura. Sus filas son compras.
- **CSV:** columnas opcionales `type` (compra, venta o dividendo) y `withholding`.

## Evolución (`domain/portfolio/holdings_performance.py`, `holdings-performance-v1`)

- **Serie diaria en euros.** Cada sesión vale lo siguiente: acciones de cada empresa × cierre guardado de ese día × cambio guardado de ese día.
  - Si a una empresa le falta el precio o el cambio ese día, la sesión se lista como hueco y se salta; nunca se rellena.
  - El dinero que entra o sale en un hueco cuenta en la siguiente sesión completa.
  - Un movimiento sin tipo de cambio bloquea el cálculo, y la pantalla dice cuál es.
- **Rentabilidad ponderada por tiempo (TWR).** Se calcula con el valor por participación de `contributions.unitised_nav` (#244), así que ni las aportaciones ni las retiradas la cambian.
- **Rentabilidad del dinero invertido (TIR).** Se calcula con `contributions.xirr` y solo con un año de historia o más, igual que la TWR anualizada.
- **Mayor caída desde un máximo.** Se mide sobre el valor por participación, con las fechas del máximo, del mínimo y de la recuperación.
- **Volatilidad anual.** Es la desviación típica de los retornos diarios (`metrics.returns_from_nav`) × √252.
- **Atribución.** Ganancia de cada empresa = valor hoy + lo cobrado al vender + dividendos netos − lo pagado al comprar, todo en euros.
  - Los puntos se calculan sobre el total comprado, así que las filas por empresa y por sector suman la rentabilidad total sobre lo comprado.
- **S&P 500 con los mismos flujos.** Se usa SPY con dividendos reinvertidos (`adj_close`) en euros:
  - compra cuando tú compras;
  - vende cuando tú vendes o cobras un dividendo, por los mismos euros y en las mismas sesiones completas;
  - si no queda SPY suficiente, se anota lo que faltó.
- **Comparación de #244.** «Tu cartera frente al S&P 500» sigue usando solo las compras; las ventas y los dividendos aparecen ahí como excluidos.

`GET /api/v1/portfolio/holdings/performance` solo lee; no descarga nada.
