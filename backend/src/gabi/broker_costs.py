"""Costes reales de eToro, calibrados contra un extracto de cuenta real
(abril-septiembre 2026) y verificados transacción a transacción — ver
README, sección "Costes reales del bróker (eToro)".

Separa dos cosas que NO son lo mismo y que un backtest de rotación de
acciones (como `multifactor_backtest.py`) no debe mezclar:

- **Coste de OPERAR** (abrir/cerrar una posición): se paga cada vez que el
  backtest rota de una empresa a otra. Es lo único relevante para
  `multifactor_backtest.run(cost_bps=...)`, porque un rebalanceo simulado
  mueve dinero entre empresas DENTRO de la cuenta, no entre el banco y
  eToro.
- **Coste de DEPOSITAR** (conversión EUR→USD al meter dinero nuevo desde el
  banco): se paga una vez por aportación real, no por cada rebalanceo. No
  tiene sentido cobrarlo en cada periodo de un backtest que no simula
  aportaciones — solo es relevante donde SÍ se simula la entrada real de
  dinero (ej. Carteras Simuladas, o una proyección de coste de cartera real).

El bróker cobra el coste de operar como una cantidad FIJA en dólares por
lado (no un %), así que pesa mucho más en posiciones pequeñas que en
grandes: 1$ es un 0.18% en una posición de 550$ y un 0.01% en una de
10.000$. Por eso no hay un cost_bps único "correcto" — depende de cuánto se
invierte por posición — y `effective_trade_cost_bps()` hace esa conversión
para un tamaño de posición concreto.
"""

# --- Coste de OPERAR: abrir o cerrar una posición (por lado) ---
# Verificado contra 61 comisiones de apertura/cierre reales del extracto
# oficial de eToro (hoja "Posiciones cerradas").
STOCK_FEE_USD = 1.00          # acciones/ETF (56/61 cargos reales, importe fijo)
STOCK_FEE_USD_HK = 2.00       # acciones de Hong Kong (1/61 cargos reales)
CRYPTO_FEE_PCT = 1.00         # criptomonedas, % del notional (4/61 cargos, ~1.000% exacto)
UK_STAMP_DUTY_PCT = 0.50      # SDRT, solo en compras de acciones cotizadas en Reino Unido

# --- Coste de DEPOSITAR: meter dinero nuevo desde el banco (conversión EUR→USD) ---
# Verificado contra el extracto oficial (comisión de conversión de divisas:
# -218.96$ agregado) y, por separado, transacción a transacción contra el
# TSV de movimientos bancarios para distinguir tarjeta de transferencia.
DEPOSIT_FX_PCT_CARD = 1.30            # tarjeta (verificado: 4/4 depósitos reales, 1.294%-1.318%)
DEPOSIT_FX_PCT_BANK_TRANSFER = 0.60   # transferencia bancaria (verificado: 24+ conversiones, ~0.60%)
# Nota: los dos primeros depósitos de la cuenta (8 y 10 de abril de 2026)
# pagaron ~0.75% en vez del 0.60% habitual — posible tarifa de arranque o
# de tramo bajo de saldo. No se usa como valor por defecto porque no se ha
# confirmado que sea la tarifa actual, solo un dato puntual observado.


def effective_trade_cost_bps(position_size_usd: float, fee_usd: float = STOCK_FEE_USD) -> float:
    """Convierte el coste FIJO de abrir/cerrar una posición (en dólares) al
    cost_bps equivalente PARA ESE tamaño de posición — el mismo coste fijo
    da un % distinto según cuánto se invierta. Devuelve un coste POR LADO,
    en el mismo formato que espera `multifactor_backtest.run(cost_bps=...)`
    (que ya lo aplica dos veces, una por lado, en `_period_returns`)."""
    if position_size_usd <= 0:
        raise ValueError("El tamaño de posición debe ser positivo.")
    return fee_usd / position_size_usd * 10000


def position_size_usd(capital_usd: float, top_n: int) -> float:
    """Tamaño de posición equiponderada dado un capital total y nº de
    posiciones — la forma más simple de estimarlo para una cartera como la
    de GABI (pesos iguales entre las top_n candidatas)."""
    if capital_usd <= 0 or top_n <= 0:
        raise ValueError("El capital y el número de posiciones deben ser positivos.")
    return capital_usd / top_n
