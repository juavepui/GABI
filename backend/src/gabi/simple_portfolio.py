"""Lógica pura detrás de 🎯 Mi cartera -- la respuesta directa a "¿qué compro?"
aplicando exactamente la hipótesis ya validada (Top-N equiponderado, pesos
congelados de app_mode.FROZEN_WEIGHTS). Vive aquí, no en la página de
Streamlit, por el mismo motivo que app_mode.py: la lógica crítica no debe
depender solo de ocultar/mostrar widgets -- tiene que poder testearse sin
navegador."""
import pandas as pd

MIN_COVERAGE = 0.7  # mismo umbral que usó el backtest real de la hipótesis congelada (multifactor_backtest.run)


def eligible_candidates(df: pd.DataFrame, min_coverage: float = MIN_COVERAGE) -> pd.DataFrame:
    """Empresas con score calculable y cobertura suficiente -- mismo criterio
    que usó el backtest real de la hipótesis congelada, no uno inventado
    aparte para esta página."""
    if df.empty:
        return df
    return df[df["composite_score"].notna() & (df["score_coverage"] >= min_coverage)]


def target_portfolio(df: pd.DataFrame, n_positions: int, min_coverage: float = MIN_COVERAGE) -> pd.DataFrame:
    """Top-N por Composite Score, equiponderado. `weight_pct` es 100/len(resultado),
    no 100/n_positions: si hay menos candidatas elegibles que las pedidas, el
    peso se reparte entre las que de verdad hay -- no se infla el resto para
    aparentar que se cubrió el hueco."""
    eligible = eligible_candidates(df, min_coverage)
    if eligible.empty or n_positions < 1:
        return eligible.iloc[0:0].assign(weight_pct=pd.Series(dtype=float))
    ranked = eligible.sort_values("composite_score", ascending=False).head(n_positions).copy()
    ranked["weight_pct"] = 100 / len(ranked)
    return ranked


def parse_holdings(text: str) -> dict:
    """`SÍMBOLO,euros` por línea -- agrega duplicados sumando en vez de
    sobrescribir (dos líneas con el mismo símbolo son dos compras distintas,
    no un error de formato). Líneas en blanco se ignoran."""
    holdings: dict[str, float] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != 2 or not parts[0]:
            raise ValueError(f"Formato inválido: {line!r}. Usa SÍMBOLO,euros.")
        symbol = parts[0].upper()
        try:
            amount = float(parts[1])
        except ValueError as exc:
            raise ValueError(f"Importe inválido en {line!r}.") from exc
        holdings[symbol] = holdings.get(symbol, 0.0) + amount
    return holdings


def allocate_new_capital(target: pd.DataFrame, current_holdings: dict, new_capital: float) -> dict:
    """Reparte `new_capital` entre las posiciones objetivo más infraponderadas
    respecto al peso igual (futuro total / nº de posiciones) -- nunca
    recomienda vender, solo dónde meter dinero nuevo. `target` debe venir de
    target_portfolio() (indexado por symbol, con columna `name`).

    Devuelve {"allocations": [...], "remaining": float, "outside_target": [...]}:
    - `allocations`: lista ordenada (más infraponderada primero) de
      {"symbol", "name", "amount"} hasta agotar `new_capital` o cubrir todos
      los huecos.
    - `remaining`: lo que sobra de `new_capital` si cubre de sobra todos los
      huecos -- no se fuerza a repartir en la propia función, la UI decide
      qué sugerir con eso.
    - `outside_target`: símbolos de `current_holdings` que ya no están en
      `target` -- informativo, nunca una recomendación de venta."""
    if new_capital < 0:
        raise ValueError("new_capital no puede ser negativo.")
    if target.empty:
        return {"allocations": [], "remaining": new_capital, "outside_target": sorted(current_holdings)}

    current_in_target = sum(current_holdings.get(s, 0.0) for s in target.index)
    future_total = current_in_target + new_capital
    target_per_position = future_total / len(target)

    gaps = []
    for symbol, row in target.iterrows():
        gap = target_per_position - current_holdings.get(symbol, 0.0)
        if gap > 0:
            gaps.append((symbol, row["name"], gap))
    gaps.sort(key=lambda item: item[2], reverse=True)

    remaining = new_capital
    allocations = []
    for symbol, name, gap in gaps:
        if remaining <= 0:
            break
        amount = min(gap, remaining)
        allocations.append({"symbol": symbol, "name": name, "amount": amount})
        remaining -= amount

    outside_target = sorted(s for s in current_holdings if s not in target.index)
    return {"allocations": allocations, "remaining": remaining, "outside_target": outside_target}
