# Revisiones de estimaciones de consenso

GABI captura EPS/ingresos de consenso, su dispersión y el
recuento de revisiones al alza/baja, como una familia de datos de
investigación separada del Composite Score. Las reglas puras están en
`gabi.domain.research.estimates`; la captura (red y escritura explícitas) en
`gabi.infrastructure.legacy.estimates` y se lanza con el trabajo `company_sync`.

## Fuente y licencia

Yahoo Finance, vía `yfinance` (`Ticker.earnings_estimate`,
`Ticker.revenue_estimate`, `Ticker.eps_revisions`) — el mismo acceso no
oficial y sin licencia formal que usa el resto de datos de Yahoo en el
proyecto (precios, fundamentales, calendario de earnings). Sin SLA: puede
cambiar de forma o dejar de estar disponible sin aviso.

## Por qué no hay reconstrucción histórica

Yahoo **no** expone un archivo point-in-time de estimaciones pasadas.
`eps_trend`/`eps_revisions` son una foto tomada *ahora*: sus columnas
relativas ("7daysAgo", "30daysAgo"...) describen cómo cambió la
estimación hasta hoy, no lo que un observador habría visto en una fecha
pasada arbitraria. No existe ninguna función de GABI que
acepte una fecha pasada y devuelva "el consenso de entonces" — hacerlo
sería inventar datos.

En su lugar, cada sincronización (`sync_estimates`) guarda la foto con
`captured_at`, la fecha real de captura. Eso construye un archivo
point-in-time **genuino**, pero que solo existe desde la primera vez que
se ejecuta — no hay atajo para tener historial anterior a esa fecha.

## Validación antes de producción

`evaluate_estimate_revision_signal()` mide Rank IC cross-seccional de
`net_revision_30d` (revisiones al alza menos a la baja, según Yahoo en el
momento de cada captura) contra el retorno futuro real — pero solo sobre
`captured_at` que de verdad se ejecutaron, nunca reconstruidos. Con pocas
capturas devuelve `status="insufficient_data"`: es el estado correcto
mientras el archivo propio de GABI sea joven, no un fallo.

En la interfaz React, este cálculo se lanza con un job explícito en modo
Research. El job solo considera capturas reales entre 2010-01-01 y el corte
observado 2025-07-02, y solo lee precios hasta ese corte. Si las capturas
disponibles son posteriores, devuelve datos insuficientes; no reconstruye ni
abre retrospectivamente un consenso que Yahoo nunca publicó. La vista de
Streamlit ya no calcula el IC al abrirse.

Esta issue queda **aparcada en la práctica** hasta que se acumulen
suficientes capturas separadas en el tiempo (por defecto: al menos 6
capturas con 20+ símbolos cada una, repartidas en 60+ días). No se ha
introducido ningún dato retroactivo para simular ese historial.

Ningún dato de esta familia entra en `scoring.py`/`screener.py`. Antes de
mezclarlo con el Composite Score hace falta un experimento registrado
explícitamente en 🔬 Research Lab, igual que cualquier otro factor
candidato nuevo.

## Dispersión del consenso

`eps_dispersion_pct = (high − low) / |avg|` es una aproximación: Yahoo no
da las estimaciones individuales de cada analista, solo el agregado
(media/mínimo/máximo/nº de analistas). No es la dispersión real del
consenso, solo un proxy de rango.
