# Puerta de datos de CBOP-v1 (#252)

**Estado:** fase 1 en ejecución con datos reales (ver el resultado al final).
No calcula ni lee rendimientos.

Es la fase 1 del preregistro propuesto en
[el mapa de hipótesis de #268](268-mapa-hipotesis.md), apartado 6. Antes de
mirar un solo retorno, la rentabilidad operativa de caja (CbOP) debe poder
calcularse para al menos el **70 %** de los miembros elegibles del S&P 500 en
cada fecha de señal. Si algún año queda por debajo, la hipótesis se cierra por
inviable, sin evaluación económica.

## Qué se mide

- **Fórmula:** `gabi.domain.research.cbop`, versión `cbop-v1`, de Ball, Gerakos,
  Linnainmaa y Nikolaev (2016):

  ```
  CbOP = (ingresos − coste de ventas − SG&A
          − Δcuentas a cobrar − Δexistencias − Δgastos anticipados
          + Δingresos diferidos + Δcuentas a pagar + Δgastos devengados) / activos totales
  ```

  - Las variaciones son las líneas `IncreaseDecreaseIn…` del estado de flujos de
    efectivo, donde un valor positivo es un aumento del saldo.
  - En XBRL, el SG&A no incluye la I+D, que se presenta en su propia línea. Es lo
    que el artículo obtiene al restar XRD del XSGA de Compustat. La I+D se guarda
    para la auditoría, pero no se resta.
- **Datos point-in-time:** solo hechos anuales de un 10-K (`fp = FY`) presentados
  **antes** de la sesión de señal.
  - El año ancla es el último balance anual presentado.
  - Si tiene más de 550 días, el emisor se considera `stale`.
- **Partidas de circulante:**
  - Una partida que el emisor no ha presentado en ningún informe anual cuenta
    como cero, y se declara en `imputed`.
  - Una que presentó otros años pero no el del ancla deja la CbOP sin valor
    (`…_stale`).
  - No se imputa nada más. Ingresos, coste de ventas, SG&A y activos son
    obligatorios.
- **Financieras:** quedan excluidas (SIC 6000–6999) y no cuentan como elegibles.
  Un emisor sin SIC conocido cuenta como elegible, y se informa en `unknown_sic`.
- **Caso de uso:** `gabi.application.research.cbop_coverage.audit`.
  - Recibe las fechas de señal (la primera sesión de julio de cada año), la
    composición, el SIC y los hechos por puertos.
  - Exige el periodo observado (`require_observed_period`, hasta el 2025-07-02).
  - Para cada fecha devuelve la cobertura, las causas de ausencia y ejemplos,
    además de una decisión `continue_to_exploratory` o `close_unfeasible`.
  - Siempre devuelve `returns_read: false`.

## Datos necesarios

Las etiquetas de SG&A, I+D y variaciones de circulante (`cbop.USD_TAGS`) no se
guardaban. Desde este cambio se añaden a las etiquetas de la sincronización SEC
(`application/market/sec_xbrl.FACT_TAGS`). Como cambia la huella de etiquetas, la
siguiente sincronización vuelve a procesar una vez el `companyfacts` de cada
emisor. Ninguna lectura existente usa estas etiquetas, así que V1, la checklist y
las métricas V2 no cambian.

## Descarga y ejecución

```powershell
uv run --project backend python -m gabi_cli research cbop-gate --download   # explícita, reanudable
uv run --project backend python -m gabi_cli research cbop-gate --audit      # escribe docs/research/cbop-v1/cobertura.json
```

- **Emisores.** Cada miembro en cada fecha de señal se asigna a su CIK con los
  intervalos de identidad histórica acreditada (`historical_identity_intervals`,
  2010–2015 y 2016–2025), en los estados `confirmed_by_multiple_evidence`,
  `confirmed_historical_ticker` y `corroborated_candidate`.
  - Un miembro sin identidad aceptada (ambigua, no resuelta o sin intervalo)
    sigue siendo elegible y cuenta como ausente (`identity_unresolved`). Así,
    las empresas que dejaron el índice pesan igual que las supervivientes.
  - No se usa el CIK por ticker actual de la sincronización operativa: un
    ticker reciclado atribuiría los hechos a otro emisor.
- **Descarga.** Se descarga el `companyfacts` y el `submissions` de cada CIK.
  - Se guardan en un almacén aparte, `data/cbop/facts.db`. La sincronización
    operativa, indexada por los tickers de hoy, no recibe símbolos deslistados.
  - Solo se conservan las etiquetas de CbOP, el SIC declarado y la huella
    SHA-256 de cada respuesta.
  - Si la SEC no tiene XBRL de un CIK, queda registrado como `absent`.
  - Se respeta el ritmo de la SEC (como máximo unas 6–7 peticiones por segundo,
    con reintentos acotados), y la descarga se reanuda donde se quedó.
- **SIC.** Es el que declara hoy el `submissions` del emisor. Un cambio de SIC
  a lo largo del tiempo no se reconstruye, y se declara como aproximación.
- **Resultado.**
  - `cobertura.json` incluye la cobertura por fecha de señal, las causas de
    ausencia, ejemplos y el resumen de la descarga, con un manifiesto SHA-256
    de las respuestas.
  - El comando nunca sobrescribe un resultado.
- **Después de la puerta.** El preregistro definitivo, con el hash del commit,
  solo se redacta si la puerta pasa en todas las fechas, y antes de cualquier
  cálculo de rendimiento. Se registra en el ledger de #60.

## Tiempo

Unas 1,5 h de trabajo asistido el 2026-11-01. La estimación del mapa para
etiquetas, auditoría y señal era de 13–21 h.
