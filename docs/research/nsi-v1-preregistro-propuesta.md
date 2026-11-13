# Propuesta de preregistro de NSI-v1 (#252)

**Estado:** propuesta pendiente de aprobación del propietario. No se ha calculado
ningún retorno. Cuando se apruebe, se congelará con el hash del commit en
`docs/research/nsi-v1/preregistro.json` y se registrará en el ledger de #60
**antes** de cualquier cálculo de rendimiento.

## Hipótesis y contaminación

- **Hipótesis.** Las empresas que reducen su número de acciones (recompras netas)
  rinden más que las que emiten. Según Pontiff y Woodgate (2008), las empresas
  emiten cuando sus acciones están caras y recompran cuando están baratas. Fama
  y French (2008) encuentran el efecto en todos los tamaños.
- **Contaminación declarada.**
  - RCF v1 (#60), que medía recompras brutas sobre FCF, ya se vio y se descartó.
    El solape es parcial: NSI mide el cambio neto de acciones y no usa FCF.
  - Ni la emisión neta ni la dilución se habían medido antes en GABI (#268,
    apartado 1).
  - No compite con ENS-VQE (#237), que no usa emisión.
- **Alternativa por defecto.** Comprar el índice. NSI tiene que demostrar que
  añade algo a eso, y a la exposición factorial conocida (CMA, RMW y UMD).

## Señal, universo y cartera

| Elemento | Propuesta |
|---|---|
| Identificador | `NSI-v1`, con la medida y la puerta de [nsi-v1-puerta-datos.md](nsi-v1-puerta-datos.md) |
| Universo | Miembros del S&P 500 en cada señal con identidad histórica acreditada, financieras incluidas. Un miembro sin dato queda fuera de la selección, nunca relleno. |
| Señal | Emisión = ln(acciones medias básicas t / t−1) del mismo 10-K. Cuanto más baja, mejor. Percentil dentro del universo con dato, sin combinar con otros factores. |
| Retardo | 10-K presentado antes de la sesión de señal. Ejecución en la apertura siguiente con el motor V3. |
| Cartera | 20 posiciones equiponderadas, como máximo 6 por división SIC. |
| Banda | Entra el quintil de menor emisión; se mantiene mientras siga en el 40 % de menor emisión. |
| Rebalanceo | Anual, en la primera sesión de julio, como en la puerta. |
| Salidas | Eventos del motor V3: fusión en efectivo o en acciones, exclusión y quiebra. |

## Flujos, costes y benchmark

| Elemento | Propuesta |
|---|---|
| Cuenta | 11.000 € iniciales y 700 € al mes. Las aportaciones esperan en caja al rebalanceo siguiente, como en la validación de #248. |
| Política | Límites de #248: emisor ≤ 10 %, sector ≤ 30 % y orden mínima con la comisión ≤ 1 %. |
| Costes | Escenarios BASE y STRESS de V3, más conversión EUR/USD y retención del 15 % sobre dividendos. |
| Benchmark primario | S&P 500 TR en EUR (#244), con el mismo calendario, los mismos flujos y la misma contabilidad. |
| Comparadores | Equiponderado del universo con dato. Regresión sobre FF5 + UMD (Ken French): si el alfa es ≈ 0, el resultado se clasifica como exposición factorial. |

## Evaluación

| Elemento | Propuesta |
|---|---|
| Fases | (1) Puerta de datos: pasada. (2) Exploratoria en 2011–2025: historia ya observada del universo; **nunca se citará como evidencia independiente**. (3) Seguimiento prospectivo desde la fecha de registro, con la primera revisión no antes de 3 años. |
| Ventanas | 2011–15, 2016–20 y 2021–25 (hasta el 2025-07-01, en el periodo observado), informadas por separado. Ninguna se elige a posteriori. |
| Test | Exceso neto mensual frente al benchmark. Cota inferior unilateral por bootstrap circular de bloques de 12 meses, con 5.000 réplicas y α = 0,05/3. |
| Presupuesto | Como máximo 3 configuraciones, todas registradas en el ledger de #60: la primaria (BASE), STRESS y Top-30 como sensibilidad. |
| Abandono | Se abandona si el exceso neto BASE es ≤ 0 en el conjunto, o si la cota inferior es < 0 en al menos dos de las tres ventanas. Si el alfa FF5+UMD tiene un intervalo centrado en ≈ 0, se reclasifica como exposición factorial y no se promociona. |
| Riesgo | Volatilidad ≤ 110 % de la del índice. Drawdown no más de 5 pp peor que el del índice (#60). Presupuesto de pérdida del 20 % (#242). |

**Potencia.** Con un tracking error del 6 % anual, una ventaja real de +2 pp
daría t ≈ 1,2 en 14 años. La fase exploratoria no puede demostrar el objetivo de
#60; solo puede descartarlo o justificar el seguimiento prospectivo.

## Trabajo antes de la evaluación

| Tarea | Horas |
|---|---|
| Ranking anual de NSI y la banda en el dominio, con tests | 3–5 |
| Adaptador V3 con el universo histórico y precios atribuidos | 4–6 |
| Conversión a EUR y retención en V3 (hoy solo en USD) | 3–5 |
| Bootstrap, regresión FF5 y artefacto | 3–5 |
