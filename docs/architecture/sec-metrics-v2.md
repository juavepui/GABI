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

## Pendiente

Valoración FCFF-WACC con puente a valor por acción, comparación de rankings
Yahoo/SEC e histórico SEC frente a V1, etiquetado de las aproximaciones V1 en la
interfaz y activación mediante una versión nueva del modelo. Validar la
calibración de selección es un estudio distinto.
