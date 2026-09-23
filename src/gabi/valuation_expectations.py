"""Valoración point-in-time frente a expectativas implícitas.

El reverse DCF es una señal descriptiva: resuelve el crecimiento constante de
FCF durante cinco años que hace coincidir el valor presente con el valor de
empresa observado. Los supuestos están fijados aquí y no se ajustan a los
resultados del backtest.
"""
import math

DEFAULT_DISCOUNT_RATE = 0.09
DEFAULT_TERMINAL_GROWTH = 0.025
DEFAULT_FORECAST_YEARS = 5


def _present_value(fcf: float, growth: float, enterprise_value: float, discount_rate: float,
                   terminal_growth: float, years: int) -> float:
    value = 0.0
    for year in range(1, years + 1):
        value += fcf * (1 + growth) ** year / (1 + discount_rate) ** year
    terminal = fcf * (1 + growth) ** years * (1 + terminal_growth) / (discount_rate - terminal_growth)
    return value + terminal / (1 + discount_rate) ** years - enterprise_value


def reverse_dcf_growth(enterprise_value: float | None, latest_fcf: float | None,
                       *, discount_rate: float = DEFAULT_DISCOUNT_RATE,
                       terminal_growth: float = DEFAULT_TERMINAL_GROWTH,
                       years: int = DEFAULT_FORECAST_YEARS) -> float | None:
    """Devuelve el crecimiento anual de FCF implícito o ``None`` si no procede.

    Se rechaza FCF no positivo, valor empresarial no positivo, una tasa de
    descuento inválida o un terminal growth que no sea menor que el descuento.
    La búsqueda está acotada a [-50%, +100%] para no presentar una solución
    numéricamente posible pero económicamente absurda como una señal válida.
    """
    if (enterprise_value is None or latest_fcf is None or enterprise_value <= 0 or latest_fcf <= 0
            or not 0 < terminal_growth < discount_rate or discount_rate <= 0 or years < 1):
        return None
    low, high = -0.50, 1.00
    f_low = _present_value(latest_fcf, low, enterprise_value, discount_rate, terminal_growth, years)
    f_high = _present_value(latest_fcf, high, enterprise_value, discount_rate, terminal_growth, years)
    if not (math.isfinite(f_low) and math.isfinite(f_high)) or f_low * f_high > 0:
        return None
    for _ in range(100):
        middle = (low + high) / 2
        f_middle = _present_value(latest_fcf, middle, enterprise_value, discount_rate, terminal_growth, years)
        if abs(f_middle) < 1e-10:
            return middle
        if f_low * f_middle <= 0:
            high, f_high = middle, f_middle
        else:
            low, f_low = middle, f_middle
    return (low + high) / 2


def expectations_metrics(*, enterprise_value: float | None, latest_fcf: float | None,
                          historical_fcf_cagr: float | None,
                          discount_rate: float = DEFAULT_DISCOUNT_RATE,
                          terminal_growth: float = DEFAULT_TERMINAL_GROWTH,
                          years: int = DEFAULT_FORECAST_YEARS) -> dict:
    implied = reverse_dcf_growth(enterprise_value, latest_fcf, discount_rate=discount_rate,
                                 terminal_growth=terminal_growth, years=years)
    return {
        "implied_fcf_growth": implied,
        "historical_fcf_cagr": historical_fcf_cagr,
        "expectations_gap": (historical_fcf_cagr - implied
                              if historical_fcf_cagr is not None and implied is not None else None),
        "expectations_discount_rate": discount_rate,
        "expectations_terminal_growth": terminal_growth,
        "expectations_forecast_years": years,
    }
