# Puerta de datos de CBOP-v1 (#252)

**Estado:** código de la fase 1 preparado, sin ejecutar con datos reales.
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

## Pendiente antes de la ejecución real

1. **Sincronización ampliada.** La sincronización normal cubre el universo
   operativo. La puerta necesita también a los miembros históricos de 2011–2025
   que ya no cotizan; si no, su ausencia sesgaría la cobertura (supervivencia).
   - Hace falta un adaptador que descargue el `companyfacts` de los CIK de la
     identidad histórica acreditada (2010–2015 y 2016–2025).
   - Es una descarga explícita a la SEC, de unas 1.000 peticiones a 10 por
     segundo como máximo, que lanza el propietario.
2. **Adaptador de lectura.**
   - Composición: `universe.get_sp500_constituents_asof`.
   - SIC: aproximación GICS de `sec_metrics_v2`, en la que Financials y Real
     Estate se tratan como financieras, declarada.
   - Hechos: los del emisor, por identidad, presentados antes de la señal.
   - Se ejecuta como comando de investigación o como job F4, y escribe el
     resultado en esta carpeta.
3. **Preregistro definitivo** con el hash del commit. Solo si la puerta pasa en
   todas las fechas, y antes de cualquier cálculo de rendimiento. Se registra en el
   ledger de #60.

## Tiempo

Unas 1,5 h de trabajo asistido el 2026-11-01. La estimación del mapa para
etiquetas, auditoría y señal era de 13–21 h.
