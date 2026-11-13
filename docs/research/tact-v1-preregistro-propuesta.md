# Propuesta de preregistro de TACT-v1 (#312)

**Estado:** propuesta pendiente de aprobación del propietario. No se ha calculado
ningún retorno. Si se aprueba, primero se pasa la
[puerta de datos](tact-v1-puerta-datos.md); después se congela con el hash del
commit en `docs/research/tact-v1/preregistro.json` y se registra en el ledger de
#60 **antes** de cualquier cálculo de rendimiento.

## Recomendación previa: no invertir tiempo ahora

Antes del diseño, la valoración honesta:

- **Poca capacidad de responder.** Con 15 años permitidos y 4 caídas fuertes, la
  diferencia de rentabilidad por unidad de riesgo entre un modelo táctico y
  mantener la inversión no se puede distinguir de la suerte. Igual que en NSI-v1
  (#252), la prueba solo podría **descartar**, no demostrar.
- **Mala relación con el plan del inversor (#242).** Aportaciones de 700 € al mes a
  largo plazo, en euros y con impuestos al vender. Un modelo que sale de la bolsa
  varias veces al año choca con aplazar impuestos, la ventaja más segura de
  mantener.
- **Ya hay contexto.** El semáforo del mercado (#308) describe el momento sin
  convertirlo en una orden.

**Propuesta:** cerrar #312 como «no se investiga ahora», con este documento como
registro de la decisión, y retomarla solo si el propietario quiere una regla de
cuánto invertir. Si aun así se quiere probar, este es el diseño.

## Hipótesis y contaminación

- **Hipótesis.** Repartir entre bolsa y refugio según el consenso de varios modelos
  tácticos publicados reduce la mayor caída desde un máximo sin perder demasiada
  rentabilidad frente a mantener siempre el 100 % en bolsa.
- **Contaminación declarada.** Ya sabemos cómo fue 2010–2025 a grandes rasgos;
  algunos modelos se publicaron con datos de ese periodo; la idea viene de ver el
  «pulso» de QuantForge del 2026-10-30.
- **Alternativa por defecto.** Comprar y mantener el S&P 500 con las mismas
  aportaciones.

## Lista cerrada de modelos

Se fijan **antes** de ver ningún resultado, a partir de su publicación. Las reglas
exactas se transcriben del artículo al congelar el preregistro; si una regla no
puede reproducirse con los datos de la puerta, el modelo sale de la lista y se
anota, sin sustituirlo.

| Modelo | Referencia | Idea de la regla |
|---|---|---|
| Media de 10 meses | Faber (2007), *A Quantitative Approach to Tactical Asset Allocation* | Bolsa si el S&P 500 cierra el mes sobre su media de 10 meses; si no, efectivo. |
| GTAA 5 (Ivy) | Faber (2007) | 5 activos (EE. UU., internacional, bonos a 10 años, inmobiliario, materias primas), 20 % cada uno, cada uno a efectivo si cae bajo su media de 10 meses. |
| Momentum dual (GEM) | Antonacci (2014), *Dual Momentum Investing* | Si el S&P 500 rinde más que las letras en 12 meses, la mejor bolsa (EE. UU. o internacional); si no, bonos agregados. |
| VAA-G4 | Keller y Keuning (2017), *Breadth Momentum and Vigilant Asset Allocation* | Momentum ponderado de 1, 3, 6 y 12 meses; si algún activo ofensivo es negativo, el mejor refugio. |
| DAA-G4 | Keller y Keuning (2018), *Breadth Momentum and the Canary Universe* | Como VAA, pero el paso a refugio lo deciden dos «canarios» (emergentes y bonos). |

**Consenso:** % en bolsa = media del % en bolsa de los 5 modelos al cierre de cada
mes. El resto, en el refugio que indica cada modelo.

## Cuenta, costes y evaluación

| Elemento | Propuesta |
|---|---|
| Cuenta | 11.000 € iniciales y 700 € al mes, en euros (#242). |
| Rebalanceo | Mensual, primera sesión del mes, con la señal del cierre anterior. |
| Costes | Comisión y diferencia de precio de V3 (BASE y STRESS) y conversión EUR/USD. |
| Impuestos | Sí: 19–30 % (base del ahorro) sobre la ganancia realizada en cada venta (`tax_drag`). Se informa antes y después de impuestos. |
| Periodo | 2010-01-01 a 2025-07-02 (`require_observed_period`); ventanas 2010–15, 2016–20 y 2021–25 por separado. |
| Medidas | Rentabilidad anual, mayor caída desde un máximo, rentabilidad por unidad de riesgo (Sharpe), tiempo fuera de la bolsa e impuestos pagados. |
| Presupuesto | 2 configuraciones en el ledger de #60: el consenso (primaria) y la media de 10 meses sola (control simple). |

**Éxito (fijado antes de mirar):** después de impuestos y con costes BASE, la
mayor caída del consenso es al menos 10 puntos menor que la de mantener **y** la
rentabilidad anual no es más de 1 punto inferior, en las tres ventanas. Si no se
cumple, se abandona y nada llega a la aplicación.

**Potencia.** No hay potencia para demostrar una mejora: el resultado, sea cual
sea, es exploratorio y no se citará como evidencia independiente.
