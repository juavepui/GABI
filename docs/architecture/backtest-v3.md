# Backtest V3 autofinanciado (#249)

`domain/portfolio/backtest_v3.py` (versión `backtest-v3`) es un motor nuevo. V1 y
V2 siguen reproduciendo sus resultados publicados; V3 no hereda su evidencia.

## Qué cambia frente a V2

| | V2 (`domain/portfolio/backtest.py`) | V3 |
| --- | --- | --- |
| Caja | Los pesos se aplican sobre todo el valor y la comisión se resta después: un rebalanceo completo puede dejar la caja negativa. | Los pesos se aplican sobre el valor neto menos una reserva para costes; primero ventas, después compras escaladas a la caja disponible. Saldo negativo solo con apalancamiento declarado, desactivado por defecto. |
| Precio | El mismo precio de la serie para señal y ejecución. | Señal al cierre de una sesión, ejecución en la apertura de la siguiente al precio nominal más medio spread y deslizamiento. |
| Liquidez | Sin límite. | Cada orden toma como mucho una parte del volumen monetario del día; el resto queda sin ejecutar y se marca parcial. Órdenes mínimas. |
| Huecos | `ffill().bfill()` rellena el inicio con precios posteriores. | Nada se rellena hacia atrás. Una barra ausente o una suspensión no negocian; la posición se valora a su último cierre y se informa como desfasada. Sin ningún precio conocido, el motor falla en lugar de inventarlo. |
| Eventos | Salidas por falta de filings. | Split, dividendo (neto de retención), fusión en efectivo o en acciones, exclusión y quiebra (con su recuperación) antes de la apertura. |

## Costes

Comisión fija y porcentual, spread (cada lado paga la mitad), deslizamiento,
participación y mínimo son parámetros (`Costs`). Escenarios declarados: `BASE`
(1 $ por orden, 5 pb de spread, 5 pb de deslizamiento, 10 % del volumen) para
grandes compañías líquidas, y `STRESS` (30 pb, 25 pb, 2 %) para mercados estrechos.

## Benchmark

`benchmark` invierte las mismas aportaciones, en el mismo calendario y con la
misma contabilidad, en un único símbolo: cada aportación se invierte en la
apertura siguiente, como lo haría un rebalanceo.

## Comprobaciones

Cada día se verifica que caja + posiciones = NAV (`identity_error`), y con
precios constantes el valor perdido es exactamente comisiones más costes de
ejecución.

## Pendiente

Adaptador de datos (precios nominales desde la caché deshaciendo los splits de
Yahoo, volumen, dividendos y eventos), job explícito con señales del ranking
histórico, comparación V2/V3 sobre los mismos datos y validación económica de la
política de #248.
