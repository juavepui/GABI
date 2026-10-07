# F7.4: primeras hojas de cálculo (#90)

Se extraen cuatro implementaciones puras, desde el commit `d50747f`, a sus
capas de dominio. El cálculo, sus constantes y sus firmas conservan el código
original; los archivos del dominio se trasladan con los mismos bytes.

| Nombre legacy | Implementación única | Consumidores antiguos pendientes |
| --- | --- | --- |
| `gabi.metrics` | `domain/market/fundamentals.py` | Screener y procedencia del ledger |
| `gabi.valuation_expectations` | `domain/market/valuation_expectations.py` | Screener histórico |
| `gabi.capital_allocation` | `domain/portfolio/capital_allocation.py` | Screener histórico |
| `gabi.broker_costs` | `domain/portfolio/broker_costs.py` | Motor de cartera V2 |

Los cuatro nombres legacy son fachadas con imports explícitos. Se mantienen
mientras existan sus consumidores; no contienen fórmulas ni duplican la
implementación. El inventario conserva esos cuatro archivos y retira la
dependencia `pandas` de `capital_allocation`. La deuda de módulos sigue en 82: esta
entrega extrae las hojas y todavía no retira sus nombres de compatibilidad.

Los adaptadores nuevos de ranking y Portfolio Lab importan directamente las
funciones/constantes del dominio. El resto de las referencias legacy conserva
su interfaz hasta que migre su flujo. No se añade I/O al dominio: sus entradas
son diccionarios, DataFrames y parámetros explícitos.

## Semántica y evidencia

Se conservan la ausencia de datos, los valores/coberturas descriptivos y los
criterios de `filed_date`, forma/duración, unidades y selección de hechos.
También permanecen los límites ya documentados de asignación de capital:
la diferencia recompra/emisión puede usar una sola pata disponible, y el
cociente de acciones no acredita dilución anual ajustada por splits.
Cambiar esas reglas requeriría una entrega financiera separada.

Las capturas futuras del ledger incluyen el hash de
`domain/market/fundamentals.py`, además del de su fachada `metrics.py`, para
identificar la implementación ejecutada. Esta nueva procedencia cambia la
versión de código de esas capturas. Los registros anteriores conservan sus
payloads, hashes y cadenas. Los 18 motores/configuración congelados y los
artefactos publicados mantienen sus bytes y hashes.

No cambia el acceso a datos ni se añade una caché; se mantienen las lecturas
y reglas de invalidación de los flujos consumidores. No se atribuye una
mejora de rendimiento a este traslado de cálculos.

## Validación

100 tests sobre métricas, costes, Screener actual/histórico, cartera V2,
Portfolio Lab, sus jobs y ledger. Ocho casos nuevos verifican que ambos
imports ejecutan la misma función, que el ranking nuevo usa el dominio,
el corte temporal y la cobertura parcial, ausencia de red/SQLite y la
procedencia del código de fundamentales.

Se comprueban además contratos/API, auditorías de inputs de capital,
arquitectura y tipos. Los tests usan datos temporales; no consultan reservas
ni recalculan estudios publicados. #90 sigue abierta para las demás hojas,
los módulos intermedios y, después, el núcleo compartido.
