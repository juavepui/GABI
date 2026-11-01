# Puerta de datos de CBOP-v1 (#252)

**Estado:** con la enmienda 1, la puerta pasa en 14 de 15 fechas. Falla en 2011 por poco (69,3 %), así que la regla da `close_unfeasible`. La decisión sobre 2011 está pendiente del propietario. No se ha leído ningún rendimiento.
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

## Resultado (2026-11-01)

**Descarga.** Se descargaron los 767 CIK con identidad aceptada: 1.534 peticiones
a la SEC, ninguna ausente.
- El resumen de la descarga, con su manifiesto SHA-256, está en
  [`cbop-v1/cobertura.json`](cbop-v1/cobertura.json).
- Ningún rendimiento se ha leído.

**Cobertura.** Por debajo del umbral del 70 % en las 15 fechas de señal:

| Señal | Elegibles | Con CbOP | Cobertura |
|---|---:|---:|---:|
| 2011-07-01 | 410 | 160 | 39.0 % |
| 2012-07-02 | 411 | 168 | 40.9 % |
| 2013-07-01 | 413 | 169 | 40.9 % |
| 2014-07-01 | 411 | 166 | 40.4 % |
| 2015-07-01 | 410 | 165 | 40.2 % |
| 2016-07-01 | 384 | 159 | 41.4 % |
| 2017-07-03 | 389 | 157 | 40.4 % |
| 2018-07-02 | 393 | 154 | 39.2 % |
| 2019-07-01 | 395 | 179 | 45.3 % |
| 2020-07-01 | 403 | 181 | 44.9 % |
| 2021-07-01 | 406 | 180 | 44.3 % |
| 2022-07-01 | 401 | 170 | 42.4 % |
| 2023-07-03 | 408 | 166 | 40.7 % |
| 2024-07-01 | 409 | 162 | 39.6 % |
| 2025-07-01 | 406 | 158 | 38.9 % |

**Causas principales**, con datos de 2020:
- **Sin coste de ventas** (`cost_of_revenue_absent`, 71 emisores). Son
  utilities, aerolíneas, cable y restauración, que presentan costes operativos
  por naturaleza y no un coste de ventas.
- **Sin SG&A** (`sga_absent`, 66). Software e internet suelen separar «ventas y
  marketing» y «generales y administrativos» (ADBE, ADSK, AMZN, ANET), así que
  no presentan la línea agregada.
- **Partidas `…_stale`** (entre 50 y 80 según el año). Son emisores que
  cambiaron de etiqueta o dejaron de presentar una partida en el año del ancla.
- **Identidad no resuelta.** Pesa poco: 6–11 emisores en 2011–2015 y ninguno
  después.

**Lectura.** La cobertura no la limita la falta de datos, sino la definición:
la fórmula de Ball et al. presupone la estructura de cuentas de Compustat, que
normaliza esas diferencias. Con la regla fijada en #268, la decisión es
`close_unfeasible`.

Hay dos caminos, y los dos se deciden antes de cualquier rendimiento:
1. **Cerrar CBOP-v1 por inviable** y pasar a la reserva (emisión neta) o
   declarar el resultado negativo en #60.
2. **Enmendar la definición de datos**, documentar la enmienda y repetir la
   puerta. La enmienda cambiaría estas reglas:
   - Sumar ventas y marketing más generales y administrativos cuando falte
     SG&A.
   - Añadir más etiquetas de coste de ventas.
   - Tratar como cero la partida de circulante que el emisor deja de presentar.

   Es una búsqueda sobre datos, no sobre retornos, pero queda registrada como tal.

## Resultado con la enmienda 1 (2026-11-01)

**Decisión.** El propietario eligió enmendar y repetir, con la condición de cerrar
si la cobertura seguía sin llegar al 70 %. La enmienda está en el commit 9c45859,
anterior a esta ejecución.

**Descarga.** Se repitió la descarga de los 767 CIK con el nuevo conjunto de
etiquetas. El manifiesto `9d08e042…` está en `cbop-v1/cobertura.json`. El
resultado anterior se conserva en `cbop-v1/cobertura-definicion-original.json`.

| Señal | Elegibles | Con CbOP | Cobertura | Pasa |
|---|---:|---:|---:|---|
| 2011-07-01 | 410 | 284 | 69.3 % | **no** |
| 2012-07-02 | 411 | 301 | 73.2 % | sí |
| 2013-07-01 | 413 | 305 | 73.8 % | sí |
| 2014-07-01 | 411 | 308 | 74.9 % | sí |
| 2015-07-01 | 410 | 312 | 76.1 % | sí |
| 2016-07-01 | 384 | 299 | 77.9 % | sí |
| 2017-07-03 | 389 | 304 | 78.1 % | sí |
| 2018-07-02 | 393 | 302 | 76.8 % | sí |
| 2019-07-01 | 395 | 346 | 87.6 % | sí |
| 2020-07-01 | 403 | 361 | 89.6 % | sí |
| 2021-07-01 | 406 | 364 | 89.7 % | sí |
| 2022-07-01 | 401 | 358 | 89.3 % | sí |
| 2023-07-03 | 408 | 361 | 88.5 % | sí |
| 2024-07-01 | 409 | 363 | 88.8 % | sí |
| 2025-07-01 | 406 | 363 | 89.4 % | sí |

**Lectura de 2011.**
- Es el año de entrada en XBRL de muchos emisores:
  - 22 no tenían todavía un 10-K con XBRL;
  - 59 no tienen una etiqueta de ingresos reconocida (variantes antiguas de
    `SalesRevenue…`);
  - 11 tienen la identidad sin resolver.
- Desde 2019 la cobertura supera el 88 %.

**Comprobación adicional.** Algunos 10-K vienen etiquetados con `fp = Q4` en lugar
de `FY` (Costco, por ejemplo, en el ejercicio 2019), y la lectura anual los
ignora. Aceptarlos no cambia la cobertura de 2011 ni la de 2012: se comprobó en
un borrador, sin modificar el código. Queda anotado como limitación conocida.

## Tiempo

Unas 1,5 h de trabajo asistido el 2026-11-01. La estimación del mapa para
etiquetas, auditoría y señal era de 13–21 h.
