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

## Pendiente

Persistencia del perfil versionado, job explícito de descarga del benchmark TR y
del EUR/USD con fuente y fecha, conexión con la cartera real de #181, escenarios
EUR/USD y de mercado, alternativas indexada/activa/mixta, API y UI.
