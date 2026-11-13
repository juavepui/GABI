"""Modela el drag fiscal español (IRPF, base imponible del ahorro) sobre el
turnover real de un backtest -- issue #14: con rebalanceo trimestral y ~63%
de turnover, las plusvalías se realizan constantemente, perdiendo el
diferimiento fiscal que sí tendría un comprar-y-mantener (cuyas plusvalías
no tributan hasta que de verdad se vende). El retorno "de mentira" del
backtest y el neto real en la cuenta pueden diferir más que el propio coste
de spread/comisión, que sí está modelado en `multifactor_backtest.py`.

Deliberadamente NO se toca el motor V1/V2 validado -- ninguno de los dos
rastrea coste de adquisición por posición/lote, así que no hay forma de
calcular una plusvalía realizada exacta desde dentro. Este módulo hace su
propia contabilidad, aparte, aproximando el coste de adquisición como
repartido uniformemente sobre toda la cartera (coste medio) -- razonable
para una cartera equiponderada y diversificada, pero NO una réplica FIFO
lote a lote de cada posición individual (ver limitaciones en el resultado)."""
import pandas as pd

# Tramos de la base del ahorro (IRPF) vigentes desde el ejercicio 2023 (Ley
# 31/2022) -- revisar cada año: cambian con la ley de presupuestos, no hay
# garantía de que sigan siendo estos cuando se lea este código.
SPANISH_SAVINGS_BRACKETS_2024 = (
    (6_000.0, 0.19),
    (50_000.0, 0.21),
    (200_000.0, 0.23),
    (300_000.0, 0.27),
    (float("inf"), 0.28),
)

LIMITATIONS = [
    "Coste de adquisición medio repartido uniformemente sobre toda la cartera -- no es FIFO lote a lote "
    "por posición individual (la ley española exige FIFO cuando se vende parcialmente el mismo valor).",
    "No modela la regla de los 2 meses (no se puede deducir una pérdida si se recompra el mismo valor, "
    "u otro sustancialmente idéntico, dentro de los 2 meses siguientes a la venta con pérdidas).",
    "El arrastre de pérdidas a años siguientes no aplica el límite legal de 4 años -- se arrastra sin límite.",
    "Un solo tramo estatal de la base del ahorro -- no distingue tramo autonómico ni deducciones personales.",
    "Liquida el impuesto de todo el año de golpe al cierre de ese año -- en la práctica se paga en la "
    "declaración de la renta del año siguiente (aprox. junio), no exactamente en ese instante.",
    "Dividendos y su retención no están incluidos -- solo plusvalías por compraventa.",
]


def progressive_tax(taxable_gain: float, brackets=SPANISH_SAVINGS_BRACKETS_2024) -> float:
    """Cuota íntegra sobre `taxable_gain` (ya neto de pérdidas compensables
    del mismo ejercicio) aplicando los tramos progresivos de la base del
    ahorro -- 0.0 si `taxable_gain` <= 0 (una pérdida neta no genera
    impuesto; ver `simulate_tax_drag` para cómo se arrastra)."""
    if taxable_gain <= 0:
        return 0.0
    tax = 0.0
    lower = 0.0
    for limit, rate in brackets:
        span = max(0.0, min(taxable_gain, limit) - lower)
        tax += span * rate
        lower = limit
        if taxable_gain <= limit:
            break
    return tax


def simulate_tax_drag(periods: pd.DataFrame, brackets=SPANISH_SAVINGS_BRACKETS_2024,
                      *, initial_capital: float = 100_000.0) -> dict:
    """Simula el drag fiscal sobre la MISMA secuencia de retornos y turnover
    ya calculada por `multifactor_backtest.run()` -- espera un DataFrame con
    columnas `fecha` (fecha del rebalanceo), `retorno` (retorno del periodo,
    ya neto de costes de fricción) y `turnover_pct` (0-100, `None`/NaN en el
    primer periodo = sin turnover, nada que se haya podido vender todavía).

    Cada periodo: la cartera crece con `retorno`; la fracción `turnover_pct`
    se vende y recompra de inmediato en las nuevas candidatas (realiza su
    parte proporcional de la plusvalía no realizada acumulada hasta ese
    momento); la fracción restante sigue diferida. Al cierre de cada año
    natural se liquida: se compensan ganancias y pérdidas realizadas ESE
    año más el arrastre de años anteriores, se aplican los tramos
    progresivos sobre el neto positivo, y el impuesto se resta del valor de
    la cartera (compone sobre menos capital a partir de ahí) -- pérdidas
    netas de un año se arrastran, sin tributar, al siguiente.

    Devuelve el valor final CON y SIN este drag fiscal para el mismo
    periodo, con el detalle año a año."""
    if periods.empty:
        raise ValueError("periods no puede estar vacío.")
    if initial_capital <= 0:
        raise ValueError("initial_capital debe ser positivo.")
    if not {"fecha", "retorno", "turnover_pct"}.issubset(periods.columns):
        raise ValueError("periods requiere las columnas fecha, retorno y turnover_pct.")

    df = periods.copy()
    df["fecha"] = pd.to_datetime(df["fecha"])
    df = df.sort_values("fecha").reset_index(drop=True)

    value = initial_capital
    pretax_value = initial_capital
    basis = initial_capital
    carry = 0.0  # pérdida neta arrastrada de años anteriores (siempre <= 0)
    year_realized = 0.0
    current_year = df["fecha"].iloc[0].year
    period_rows = []
    tax_by_year: dict[int, dict] = {}

    def _settle_year(year: int):
        nonlocal value, carry, year_realized
        net = year_realized + carry
        taxable = max(net, 0.0)
        tax = progressive_tax(taxable, brackets)
        value -= tax
        tax_by_year[year] = {"realized_net": net, "taxable": taxable, "tax": tax}
        carry = min(net, 0.0)
        year_realized = 0.0

    for _, row in df.iterrows():
        year = int(row["fecha"].year)
        if year != current_year:
            _settle_year(current_year)
            current_year = year

        ret = float(row["retorno"])
        turnover = 0.0 if pd.isna(row["turnover_pct"]) else float(row["turnover_pct"]) / 100
        if not 0.0 <= turnover <= 1.0:
            raise ValueError(f"turnover_pct fuera de rango en {row['fecha'].date()}: {row['turnover_pct']}.")

        pretax_value *= (1 + ret)
        new_gross = value * (1 + ret)
        realized_gain = turnover * (new_gross - basis)
        year_realized += realized_gain
        basis = turnover * new_gross + (1 - turnover) * basis  # recomprado a coste actual + lo mantenido a su coste viejo
        value = new_gross

        period_rows.append({
            "fecha": row["fecha"], "year": year, "turnover": turnover,
            "realized_gain": realized_gain, "value_pretax_running": pretax_value, "value_aftertax_running": value,
        })
    _settle_year(current_year)  # liquida el último año aunque esté incompleto

    total_tax = sum(y["tax"] for y in tax_by_year.values())
    return {
        "initial_capital": initial_capital,
        "final_value_pretax": pretax_value, "final_value_aftertax": value,
        "pretax_return": pretax_value / initial_capital - 1,
        "aftertax_return": value / initial_capital - 1,
        "tax_drag_pct_points": (pretax_value / initial_capital) - (value / initial_capital),
        "total_tax_paid": total_tax,
        "unrealized_gain_remaining": pretax_value - basis,
        "tax_by_year": tax_by_year, "n_periods": len(df), "n_years": len(tax_by_year),
        "periods_detail": pd.DataFrame(period_rows), "limitations": LIMITATIONS,
    }


def zero_turnover_periods(periods: pd.DataFrame, return_column: str) -> pd.DataFrame:
    """Construye un `periods` compatible con `simulate_tax_drag` para un
    comprar-y-mantener puro (turnover 0 en todos los periodos) a partir de
    la columna de retorno de un benchmark ya presente en el backtest (ej.
    `periods["spy"]`) -- para comparar el drag fiscal de la estrategia
    contra el de no vender nunca durante el mismo tramo temporal."""
    if return_column not in periods.columns:
        raise ValueError(f"periods no tiene la columna {return_column!r}.")
    return pd.DataFrame({
        "fecha": periods["fecha"], "retorno": periods[return_column], "turnover_pct": 0.0,
    })
