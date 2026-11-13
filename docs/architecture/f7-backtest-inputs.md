# Backtests V1/V2 con entradas explícitas (F7.24, #132)

Segunda entrega de #132. Los bucles de `multifactor_backtest` (V1) y
`portfolio_backtest` (V2) pasan a casos de uso que reciben todas sus entradas:

| Pieza | Ahora |
| --- | --- |
| Entradas | `application/research/backtest_market.BacktestMarket`: composición histórica, ranking a fecha, calidad del ranking, precios atribuidos, últimos filings SEC, propietario del ticker, valor de salida acreditado, calendario NYSE, fecha de hoy y tasa libre de riesgo |
| Bucle V1, retorno por periodo, curvas diarias | `application/research/backtest_v1` (`run`, `period_returns`, `required_symbols`, `daily_capital_curve`, `daily_benchmark_curve`) |
| Bucle V2, valoración diaria, salidas 2010-2015, comprar y mantener | `application/research/backtest_v2` (`run`, `daily_segment`, `historical_exits`, `buy_and_hold_curve`) |
| Reglas puras | `domain/portfolio/backtest`: muestreo con semilla, métricas de riesgo por periodo y diarias (la tasa libre de riesgo es un parámetro), banda de permanencia, error del Sharpe, operación, rebalanceo y liquidación de salidas |

El código se ha movido sin cambios de fórmula ni de orden de operaciones. La única
diferencia es de dónde salen los datos.

## Fachadas

`multifactor_backtest.market()` construye en cada llamada el mercado operativo con los
módulos de siempre (`universe`, `screener_asof`, `data_quality`, `identity`,
`historical_pit`, `exchange_calendars`, `date.today`, `config.RISK_FREE_RATE`). Cada
fuente se resuelve en el momento de la llamada, así que siguen valiendo:

- los parches de `full_universe_audit` (`v1._period_returns`, `v2._daily_segment`,
  `screener_asof.build_ranking_as_of`), de `rotation_experiment` (`v2._rebalance`) y de
  `r3_experiment` (`config.DB_PATH`), todos congelados. `run` recibe
  `_period_returns`, `_rebalance` y `_daily_segment` como funciones que se buscan en el
  módulo en cada periodo;
- la llamada directa de `overfitting_audit` a `bt._period_returns`;
- los nombres que leen Portfolio Lab y otros consumidores: `_sample_symbols`,
  `_MAX_DAYS_WITHOUT_FILING`, `_rebalance_to_weights`, `_apply_trade`, `_settle_exits`,
  `_historical_exits`, `VALID_MODES`, `daily_risk_metrics`, `sharpe_standard_error`.

`multifactor_backtest.py` y `portfolio_backtest.py` siguen existiendo:
`overfitting_audit` lee el primero por nombre y `full_universe_audit` registra ambos en
la huella de sus cachés. Como la pila ya cambia `screener_asof.py` e `identity.py`, que
están en la misma huella, las cachés locales de `full_universe_audit` se invalidan una
sola vez al integrarla; esta entrega no añade otra invalidación.

Inventario: `portfolio_backtest` pierde `exchange_calendars`, `data_quality`,
`historical_pit`, `identity`, `screener_asof` y `universe`; `multifactor_backtest`
pierde `numpy` (−7). Las pruebas de V2 parchean ahora `gabi.universe` y
`gabi.screener_asof` directamente; antes lo hacían a través de `pb.`, pero es el mismo
módulo.

## Validación y medida

`test_backtest_inputs_migration.py` con `backtest_inputs_migration.json` (código de
`ad0d279`). Sobre un mercado sintético de 10 símbolos y 2021-2023 con calendario NYSE
real, ejecuta los módulos capturados, las fachadas nuevas y los casos de uso con un
`BacktestMarket` explícito que no toca ningún módulo antiguo, y compara exactamente
(sin tolerancia) periodos, rentabilidades, costes, NAV, métricas, saltos y eventos de
salida. Cubre la banda de permanencia, el umbral de rotación, el muestreo, el coste nulo
de lo mantenido, el ticker reciclado, el precio ausente, la salida acreditada (EXT), la
composición no exacta y un periodo sin salida. Dos mutaciones deliberadas (cobrar coste
a lo mantenido; adelantar las salidas acreditadas) hacen fallar las pruebas.
Validación del 2026-10-14: suite Python completa de 2.129 pruebas correcta y `research
frozen --typecheck` sin diagnósticos nuevos.

Medida: `.venv/Scripts/python.exe scripts/measure_f7_backtests.py`. Windows/Python 3.13,
mediana de 25, mismo mercado sintético. Dos ejecuciones:

| Backtest | Anterior (s) | Nuevo (s) |
| --- | --- | --- |
| V1 (`top_n=5`) | 0,101 / 0,120 | 0,106 / 0,121 |
| V2 (`top_n=4`) | 0,111 / 0,139 | 0,117 / 0,122 |

Sin cambio apreciable: la variación entre ejecuciones es mayor que la diferencia.
Construir el mercado cuesta unos 30 µs y el acceso a datos no cambia (mismas llamadas
a `identity.backtest_prices`/`last_filings`).
