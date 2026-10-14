# Retirada de `data_fetch` (F7.30, #90/#91)

`data_fetch` mezclaba descargas de Yahoo, reglas de caducidad y la orquestación de los
refrescos. Se reparte así:

| Pieza | Ahora |
| --- | --- |
| Columnas de un ticker en una descarga por lotes, splits, señal mínima de fundamentales, precio ajustado a una fecha, «126 cierres recientes», estado de un snapshot de fundamentales, fundamentales caducados y fallos por empresa | `domain/market/yahoo_data.py` |
| Historia hasta una fecha (`price_history_asof`), precios para decisiones (`decision_prices`) y refresco del universo (`universe_data`) | `application/market/market_downloads.py`, con puertos |
| Descargas por lotes con sus pools (`fetch_prices_batch`, `fetch_splits_batch`, `fetch_fundamentals_batch`), `sync_prices`, clasificación de errores y la composición con la identidad temporal y `config` | `infrastructure/legacy/data_fetch.py` (mismos nombres públicos) |
| `refresh_data` (Yahoo + SEC EDGAR con fallos por empresa) | se mueve de `screener` al puente: solo lo llaman `infrastructure/legacy/{data_update,jobs,periodic}` |

`screener` deja de importar `data_fetch` y `edgar`. Está en `model_version`, pero la
pila #122→#150 ya lo modifica: esta entrega no añade otro cambio de huella.
`earnings` y `estimates` usan `domain.market.price_sync.yahoo_symbol`, que era lo que
hacía `normalize_symbol`. Se elimina `_is_stale_trading_day`, que no usaba nadie.
El puente ya no está exento de mypy.

## Pruebas

- `test_data_fetch_migration` compara con el código capturado justo antes
  (`fixtures/data_fetch_migration.json`, incluido el `refresh_data` de `screener`):
  refresco del universo dos veces y con `force`, `refresh_data` con fallos SEC,
  historia a dos fechas (con símbolos cubiertos, sin identidad, sucesor y descarga
  fallida) y precios para decisiones. Coinciden resultados, progreso, tablas de SQLite
  y llamadas a Yahoo.
- Las capturas antiguas que importaban `gabi.data_fetch` (`history_refresh`, `macro`,
  `insider`) lo reciben como el puente solo dentro de su prueba.
- Las pruebas que sustituían `screener.refresh_data` sustituyen el del puente.

Inventario: 61 módulos planos = 18 congelados + 40 permanentes + 3 pendientes.
