# Aportaciones y benchmark en EUR (#244)

`domain/portfolio/contributions.py` (perfil `investor-profile-v1`) define, sin I/O,
cómo se compara una cartera con el benchmark recibiendo los mismos euros los
mismos días.

## Perfil

Capital inicial, aportación mensual, horizonte de evaluación, tolerancia de
pérdida, fecha en que se necesita el dinero (opcional) y residencia fiscal
(opcional, la fiscalidad solo se aplica si está confirmada).
`capital_need_before_horizon` avisa si el dinero se necesita antes de terminar el
horizonte: hay que aclararlo antes de recomendar exposición real. La tolerancia
es un umbral de revisión, no una garantía ni una venta automática.

## Simulación

- Precios de rentabilidad total: los dividendos ya están en la serie y no se suman.
- Un ETF real cotiza neto de TER; solo un índice teórico lleva `annual_cost_pct`.
  Así los costes no se cuentan dos veces y el vehículo invertible queda separado
  del índice.
- El cambio es una sola serie fechada en divisa del vehículo por euro.
- Comisión fija y porcentual, coste de conversión, importe mínimo y fracciones o
  acciones enteras son configurables. Los costes se descuentan de la aportación.
- Una aportación se ejecuta en la primera sesión con precio y cambio desde su
  fecha; sin datos queda pendiente y se informa, nunca se rellena.

## Rendimiento

- **Habilidad**: TWR sobre un NAV unitizado (los flujos entran al cierre) y su
  drawdown, que el dinero nuevo no oculta.
- **Experiencia**: XIRR, riqueza final, pérdida sobre aportaciones y euros
  perdidos; también euros en riesgo con la tolerancia.
- `compare` exige aportaciones idénticas.

## Perfil persistente y benchmark (parte 2)

- `infrastructure/storage/investor_profile.py`: cada guardado añade una revisión a
  `investor_profiles`; las anteriores no cambian. Un GET no crea la tabla.
- `application/portfolio/benchmark.py`: el plan del perfil (por defecto desde hace
  un horizonte) compra SPY con los costes del bróker del perfil. Lee de la caché
  el cierre ajustado de SPY (dividendos reinvertidos brutos, sin retención; precio
  neto de TER) y `USDEUR=X`. Sin caché responde 409; nunca descarga.
- El job explícito `benchmark_prices` descarga SPY y `USDEUR=X`.
- API: `GET/POST /api/v1/portfolio/investor/profile` y
  `GET /api/v1/portfolio/investor/benchmark?start=`; la respuesta declara fuente,
  serie, primeras y últimas fechas de precio y de cambio, y la revisión del perfil.

## Cartera real frente a SPY (parte 3)

`lots_history` convierte las compras de #181 en flujos: coste con comisión al
cambio que aplicó el bróker o, si falta, al cambio en caché de su fecha. Su valor
sigue el cierre ajustado desde la compra (rentabilidad total, como el benchmark;
la valoración de «Mi cartera» sigue siendo de precio). Una compra sin precio o
cambio de su fecha se excluye y se informa; una sesión con huecos de más de cinco
sesiones se descarta y sus flujos entran en la siguiente completa. SPY recibe
exactamente esos flujos. `GET /api/v1/portfolio/investor/holdings-benchmark`.

## Índice teórico y vehículo invertible (parte 5a)

El benchmark del plan devuelve también `vehicles`: las mismas aportaciones en
`^SP500TR` (índice total return teórico: sin costes, conversión ni retención) y en
`SXR8.DE` (iShares Core S&P 500 UCITS Acc en Xetra, en EUR: acumula dividendos tras
la retención, precio neto de TER, con los costes del bróker y sin conversión). La
diferencia entre ambos es el coste real de invertir el índice. Sin precios en
caché, el vehículo se marca `missing_prices` sin bloquear el resto. El job
`benchmark_prices` descarga los cuatro símbolos.

`yahoo_symbol` conserva los sufijos de bolsa (`.DE`, `.L`, `.MC`, `.PA`, `.AS`,
`.MI`, `.SW`) y solo convierte las clases de acciones de EE. UU. (BRK.B → BRK-B).

## Escenarios y alternativas (parte 5b)

- `scenarios`: efecto inmediato en euros de choques declarados (mercado −10/−20/−35 %,
  euro ±10 %, mercado −20 % con euro +10 % y hueco de apertura −7 %). Un activo en
  dólares pierde `1 − 1/(1 + e)` en euros si el euro sube `e`. El plan del perfil
  tiene exposición al dólar del 100 %; la cartera real, la parte de su valor actual
  no cotizada en EUR (aproximación por divisa de cotización). Superar la tolerancia
  significa revisar el plan, nunca vender.
- `alternatives`: cada compra real repartida entre la cartera activa y SPY al 0, 25,
  50, 75 y 100 %. La parte activa escala acciones y comisión de cada compra; la del
  índice paga los costes del bróker sobre su parte. Es un rango para comparar: GABI
  no recomienda pesos.

Con esto la #244 queda cubierta en su alcance de producto; la fiscalidad requiere
residencia confirmada y no se calcula todavía.
