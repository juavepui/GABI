# Retirada de `app_mode` (F7.33, #90/#91)

`app_mode` duplicaba, sobre ficheros y ledgers locales, lo que la aplicación ya resuelve
en sus capas:

| Antes (`app_mode`) | Ahora |
| --- | --- |
| `FROZEN_MODEL_ID`, `FROZEN_WEIGHTS`, `weights_match_frozen`, `model_status`, `experimental_banner_message` | `domain.market.model_policy` (los pesos congelados son de solo lectura; quien necesita un `dict` hace `dict(...)`) |
| `get_mode`/`set_mode` sobre `app_mode.json` | `infrastructure/storage/mode.FileMode` (escritura atómica) y `ReadOnlyMarket.local_model` (lectura), mismo fichero |
| `current_model_status` | `application/administration/model.ModelQueries` con `ReadOnlyMarket.local_model`: validación ciega bloqueada con rebalanceos y pesos congelados como señal fuerte, experimento `LIVE_FORWARD` como débil |

Los únicos consumidores de producción eran `live_ledger` y `evidence_confidence`, que
solo leían el identificador y los pesos congelados; ahora los toman de `model_policy`.
`live_ledger.model_metadata` ya hasheaba `domain/market/model_policy.py` y nunca
`app_mode.py`; ambos módulos cambian ya en la pila, así que esta entrega no añade otro
cambio de `model_version`.

Dos diferencias de la ruta de producción respecto a la fachada, que no tenía
consumidores: en modo Investor el estado usa siempre los pesos congelados, y un
`app_mode.json` corrupto devuelve `local_state_error` (503) en vez de suponer Investor.

## Pruebas

- `test_model_state` sustituye a `test_app_mode`: recorre por la API real los mismos
  escenarios (modo por defecto y guardado, pesos congelados y personalizados, señal débil,
  señal fuerte que gana, validaciones que no cuentan: sin rebalanceos, otros pesos o sello
  roto) y prueba las reglas puras sobre `model_policy`. La prueba de `record_rebalance`
  pasa a `test_blind_validation`.
- `test_research_ledgers_migration` deja de comparar `current_model_status` con la
  fachada capturada: la fachada ya no existe y sus escenarios están en `test_model_state`.
- `test_api` comprueba la compatibilidad con el selector antiguo leyendo y escribiendo
  `app_mode.json` directamente.
- `backend/tests/retired_modules.py` añade un sustituto de `app_mode` para los scripts que
  ejecutan capturas.

Inventario: 58 módulos planos = 18 congelados + 40 permanentes + 0 pendientes.
