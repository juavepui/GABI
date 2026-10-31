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

## Pendiente

Escenarios EUR/USD y de mercado, alternativas indexada/activa/mixta, índice TR
teórico frente a vehículo de acumulación, y la UI.
