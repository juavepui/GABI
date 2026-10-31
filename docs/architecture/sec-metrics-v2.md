# Métricas SEC V2 (#245)

`domain/market/sec_metrics_v2.py` (versión `sec-metrics-v2`) define métricas
fundamentales con ausencias explícitas y procedencia por input. No sustituye a
`sec_facts.py`: las tres pruebas prospectivas ejecutan ese camino en vivo y no
cambia de semántica ([registro de estudios](../studies/README.md), ADR 0008).

## Estados

Cada input es un `Fact` con etiqueta, unidad, periodo, accession y fecha de
presentación. `reported_zero` solo se da con un `0` declarado; un componente no
presentado es `absent`, y uno presentado para otro ejercicio es `stale`. Nunca se
infiere cero por omisión XBRL. Cada `Metric` declara su `convention` y su motivo
cuando no se calcula: `absent`, `stale`, `not_applicable` o `not_meaningful`.

## Definiciones

- **Deuda financiera**: `LongTermDebt` (incluye la parte corriente) o, si falta,
  `LongTermDebtNoncurrent` + `LongTermDebtCurrent`; más `ShortTermBorrowings` o
  `CommercialPaper` si se presentan. Sin componente a largo plazo, la deuda es
  ausente.
- **Caja**: `CashAndCashEquivalentsAtCarryingValue` más inversiones a corto plazo
  si se presentan. Excluye el efectivo restringido.
- **EV** = capitalización + deuda financiera − caja.
- **ROIC** = NOPAT / capital invertido medio. NOPAT = resultado operativo × (1 − tipo
  efectivo), con tipo = impuesto / resultado antes de impuestos acotado a [0, 1). Si
  el resultado antes de impuestos no es positivo o falta el impuesto, se usa el 21 %
  legal y se declara. Capital invertido = patrimonio + deuda financiera − caja, media
  del balance de apertura y de cierre; sin balance de apertura no se calcula.
- **Sectores financieros** (SIC 6000–6199, 6300–6411 y 6798): ROIC y EV no aplican.

Solo cuentan valores anuales completos (340–380 días) de 10-K y 10-K/A; para cada
cierre gana la presentación más reciente, y dos valores distintos en la misma
presentación anulan ese ejercicio.

## Valoración FCFF-WACC

`domain/market/valuation_v2.py` (versión `valuation-v2-fcff-wacc`) sustituye, para
la V2, el reverse DCF de `valuation_expectations` (CFO − capex frente a EV con
9 %/2,5 % fijos), que sigue en los caminos activos.

- **FCFF** = flujo operativo + intereses pagados × (1 − t) − capex. Sin capex o sin
  intereses pagados es ausente; los intereses pueden faltar solo con deuda
  financiera declarada cero.
- **WACC** = E/(D+E)·(rf + β·ERP) + D/(D+E)·kd·(1 − t), con E la capitalización y D
  la deuda contable (aproximación declarada de su valor de mercado). kd = gasto
  financiero / deuda al cierre si está en (0, 25 %]; si no, el kd de reserva de la
  versión del modelo, declarado como `kd=assumed`.
- **DCF**: FCFF creciendo a `g` durante el horizonte más valor terminal de Gordon;
  no se calcula si el crecimiento terminal no es menor que la WACC o el FCFF no es
  positivo.
- **Puente**: valor del capital = EV del DCF − deuda financiera + caja; valor por
  acción = capital / acciones diluidas medias. Capital no positivo: `not_meaningful`.
- **Crecimiento implícito**: el `g` constante que iguala el DCF al EV observado,
  buscado en [−50 %, +100 %].

rf, ERP, β, kd de reserva, horizonte y crecimiento terminal son `Assumptions` que
fija la versión del modelo que active la valuación; el dominio no los fija. El
valor baja con la WACC y la β y sube con el crecimiento y la caja; con más deuda
no es monótono, porque abarata el capital.

## Comparación con V1 (#245)

El job explícito `metrics_comparison` (Administración › Calidad de los datos)
compara, sobre la caché y sin escribir:

- **ROIC V1 frente a V2** con los mismos hechos SEC presentados hasta la fecha:
  estados y motivos de la V2, acuerdo de orden (Spearman), quintil alto compartido,
  diferencia mediana, mayores diferencias y los casos en que V1 daba un número que
  V2 declara ausente o no aplicable.
- **Hoy** además: EV de Yahoo frente al EV SEC V2 y el ranking operativo puntuado
  con cada ROIC (Top-20 compartido, entradas y salidas).
- **Fecha pasada** (solo histórico observado 2010–jul. 2025; nunca una reserva):
  únicamente hechos SEC presentados hasta esa fecha, porque Yahoo y el ranking en
  caché no son point in time.

El sector financiero se aproxima con GICS (Financials y Real Estate), declarado en
el informe. La sincronización SEC guarda también `CommercialPaper`, `InterestPaid`
e `InterestPaidNet`; las métricas V1 no los leen. Una corrección de definición no
demuestra alfa: la calibración de selección es un estudio distinto.

## Pendiente

Activación mediante una versión nueva del modelo que use estas métricas y fije las
`Assumptions` de la valoración, sin cambiar los caminos de los estudios activos.
