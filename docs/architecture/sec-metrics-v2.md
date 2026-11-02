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

## Persistencia y versión de métricas del modelo

La tabla `sec_metrics_v2` guarda una fila por emisor con la versión de métricas, el
cierre anual de referencia, el ROIC V2 con su estado, motivo, convención e inputs
(etiqueta, periodo, accession y presentación), y la deuda financiera y la caja con su
estado, para construir el EV con una capitalización. La V1 (`edgar_metrics`) no cambia
y la tabla nueva no entra en la huella de datos.

- **Una sola ruta de cálculo**: la fila se calcula siempre desde los hechos guardados
  del emisor (`application/market/stored_metrics_v2.py`), con la misma reconstrucción
  que la comparación. Un test comprueba que coincide con el cálculo sobre el
  companyfacts descargado.
- **Cuándo se escribe**: la sincronización SEC la recalcula cuando cambian los hechos
  de un emisor. Al terminar cada actualización de datos, `fill` escribe las filas que
  faltan o son de otra versión, sin descargar; cuando todas están al día, solo hace una
  consulta.
- **Sector**: la fila se calcula como no financiera; quien la lee aplica la regla de
  sector con el proxy GICS (Financials y Real Estate), igual que la comparación.

`ModelVersion.metrics_version` declara con qué métricas SEC puntúa una versión:
`sec-metrics-v1` (por defecto, y la única admitida para la hipótesis sellada
GABI-MF-v1) o `sec-metrics-v2.1`. Con la V2, el ranking activo toma el ROIC de
`sec_metrics_v2`. Una fila ausente, de otra versión, no calculada o de un emisor
financiero deja el ROIC ausente, nunca el valor V1. El crecimiento y los enlaces siguen
saliendo de `edgar_metrics`. La comparación V1/V2 usa siempre el ranking V1 como base.

## Versión 2.1 y activación (2026-11-02)

La comparación con datos reales mostró que V2 solo calculaba el ROIC de 217 empresas,
frente a 428 con V1. Antes de activarla se mejoró, y la definición resultante es
**`sec-metrics-v2.1`**:

- **#281:**
  - Cada componente toma, para el ejercicio ancla, la primera etiqueta candidata que
    presenta ese año. El año de apertura y el ancla buscan en todas las etiquetas de
    patrimonio.
  - Se añaden las etiquetas de deuda con arrendamientos tras ASC 842.
  - Una empresa que **nunca** ha presentado deuda ni intereses en un informe anual
    tiene deuda `assumed_zero`, declarada en los insumos (decisión del propietario).
- **#282:**
  - Sin línea de beneficio operativo se usa el EBIT aproximado, declarado en la
    convención (`ebit_proxy=pretax+interest`).
  - Si la caja simple dejó de presentarse, se usa la que incluye la restringida.

Las filas guardadas como `sec-metrics-v2` se recalculan con la versión 2.1.

**Cobertura del ROIC V2.1:** 334 empresas no financieras, frente a unas 338 con V1.
- El EV V2 coincide con el de Yahoo: diferencia mediana de −1,6 % en 358 empresas.
- Puntuar con ella cambia 4 de las 20 primeras del ranking.

**Activación.** El propietario activó **`GABI-MF-v2`** (`infrastructure/model_versions.py`):
- mismos pesos, parámetros técnicos, benchmark y tipo libre de riesgo que v1, con
  `metrics_version="sec-metrics-v2.1"`;
- empieza **sin evidencia propia** y se muestra EXPERIMENTAL (ADR 0008);
- GABI-MF-v1 sigue sellada, y los caminos de los estudios activos (ENS, #43 y #44)
  no cambian.

`create_app(model=...)` permite fijar la versión. Los tests de la hipótesis sellada
pasan GABI-MF-v1 explícitamente. La valoración V2 (FCFF-WACC) no forma parte del
score y no necesita supuestos en la versión del modelo.
