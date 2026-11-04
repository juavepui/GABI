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

## Desdoblamientos y agrupaciones de acciones (#305)

Un desdoblamiento (split) cambia cuántas acciones tienes y su precio por acción,
sin crear una ganancia o una pérdida por sí mismo. Un contrasplit hace la operación inversa.

- Anota las cantidades y el precio originales de cada compra o venta. Si el bróker
  ha reajustado **ambos** a una fecha posterior, indica esa fecha en el formulario
  o en la columna opcional `basis_date` del CSV. No mezcles cantidades reajustadas
  con precios originales. Los movimientos antiguos se interpretan en la fecha del movimiento.
- La conversión es de lectura: no modifica los movimientos guardados, sus importes,
  comisiones ni dividendos. También concilia ventas, coste medio, atribución y plan de aportaciones.
- La evolución usa una misma base de acciones y precios para toda la serie. Las
  cantidades y precios mostrados en la posición se expresan en la fecha de valoración.
- «Actualizar precios de mi cartera» obtiene precios y eventos de la misma respuesta
  y guarda por empresa una copia atómica exclusiva de cartera, con fuente y fecha.
  Incluye la confirmación de que no hubo eventos cuando la fuente devuelve cero.
- Un historial antiguo sin verificación emparejada muestra un aviso explícito:
  no debe usarse para decidir hasta actualizar. Eventos inválidos o duplicados
  bloquean la valoración; nunca se estima un split por un salto de precio.
  Las posiciones sin verificar se excluyen del plan de aportaciones y del panel de riesgo,
  que las declaran sin valorar.
- Los snapshots se reemplazan solo mediante la actualización explícita. No hay
  caché de cálculos: las consultas leen las filas guardadas por empresa, con límite
  de 30 símbolos y 10000 sesiones por símbolo. Los GET no escriben ni descargan.

## Evolución (`domain/portfolio/holdings_performance.py`, `holdings-performance-v2`)

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

## Verificación de #305

`backend/tests/test_holdings_splits.py` comprueba con cuentas independientes:
split 2:1, contrasplit 1:10, compras/ventas a ambos lados del evento, cantidades
reajustadas del bróker, valoración anterior al evento con precios en base actual,
dividendos, eventos inválidos, rollback conjunto, consultas sin efectos y conexión del worker.
No usa datos reales ni abre reservas. La prueba de navegador de Mi cartera verifica
el formulario y el aviso de datos sin verificar.

Medición local sintética (30 símbolos, 2610 filas desde 2026-06-01, cinco lecturas;
mediana en Windows, sin red): lector previo de simulaciones 31 SELECT / 71,11 ms /
146160 bytes de DataFrames; lector emparejado de cartera 4 SELECT / 55,10 ms /
62640 bytes. El nuevo lector solo carga cierre y cierre ajustado en la ventana
pedida, con los eventos fuera de ventana necesarios para reconstruir su base.
Es una medición pequeña, no una garantía de tiempos en la base del propietario.
