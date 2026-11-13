# Riesgo por emisor y política de cartera (#248)

Avisar de una concentración (#180) no limita la exposición. La política de
`domain/portfolio/risk_policy.py` (versión `portfolio-policy-v1`) sí la limita, y se
versiona aparte de los modelos: cada guardado es una revisión en
`portfolio_policies`, con el mismo almacén de revisiones que el perfil de #244. No
activa ninguna cartera ni envía órdenes.

## Política

- Peso máximo por emisor y por sector. Dos clases de un mismo emisor (BRK-A y
  BRK-B) se resuelven a la misma entidad SEC y cuentan como un solo riesgo.
- Sin apalancamiento: pesos y caja suman exactamente 1. El exceso de un grupo
  limitado se reparte a prorrata entre posiciones con margen; lo que no cabe queda
  en caja.
- Reserva de caja opcional.
- Elegibilidad: precio en caché y volumen diario en dólares mínimo.
- Coste máximo por orden: una orden más cara se agrupa con otras.

## Panel de Mi cartera (`GET /api/v1/portfolio/risk`)

Peso por emisor, sector, industria, moneda de cotización y exposición económica
(un miembro del S&P 500 cuenta en USD aunque cotice en otra moneda; aproximación
declarada), inclinación media a los factores de GABI y liquidez en sesiones al
ritmo de participación. Estrés: caída de mercado a través de la beta de cada
posición, la misma caída con correlaciones en 1, euro +10 % y ambos a la vez. El
umbral de pérdida es de revisión: un hueco de apertura o una posición ilíquida
pueden superarlo antes de poder actuar.

## Propuesta (`GET /api/v1/portfolio/risk/proposal`)

La selección Top-N congelada con pesos iguales frente a la misma selección con
los límites de la política, y las compras que necesitaría una aportación con los
costes del perfil (comisión, conversión, mínimo, fracciones). Solo compras: las
mayores desviaciones primero, con efectivo residual. El número de posiciones lo
fija el inversor; no se optimiza para mejorar resultados históricos.

## Pendiente

Validación económica (rotación, exceso neto y drawdown frente al benchmark
comparable) con el motor de backtest de #249.
