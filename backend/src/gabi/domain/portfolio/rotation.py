"""Regla de sustitución ex ante para limitar rotación innecesaria.

La señal es el ``composite_score`` del ranking; esta función solo decide qué
posiciones pasan a ejecución. Un valor positivo de ``hurdle_points`` exige que
la candidata nueva mejore a la posición más débil que se conserva por más
puntos de Composite. El umbral se fija antes del backtest y no se calibra con
su rentabilidad. Las comisiones y el spread se cargan después en el motor de
cartera, de modo que la decisión y la ejecución quedan separadas.
"""


def select_with_score_hurdle(previous_picks: list[str] | None, ranked_pool: list[str],
                             scores: dict[str, float], top_n: int,
                             hurdle_points: float = 0.0) -> list[str]:
    """Selecciona ``top_n`` posiciones aplicando un umbral de sustitución.

    Con ``hurdle_points=0`` devuelve exactamente el top-N estricto. Con un
    umbral positivo conserva posiciones anteriores elegibles hasta que una
    candidata las supere por más puntos. El orden del resultado sigue el orden
    del ranking salvo por las posiciones retenidas; no modifica ninguna entrada.
    """
    if top_n < 1:
        raise ValueError("top_n debe ser positivo.")
    if hurdle_points < 0:
        raise ValueError("hurdle_points debe ser >= 0.")
    ranked = list(dict.fromkeys(ranked_pool))
    strict = ranked[:top_n]
    if hurdle_points == 0 or not previous_picks:
        return strict

    eligible = set(ranked)
    picks = []
    for symbol in previous_picks:
        if symbol in eligible and symbol not in picks:
            picks.append(symbol)
        if len(picks) == top_n:
            break

    for candidate in ranked:
        if candidate in picks:
            continue
        if len(picks) < top_n:
            picks.append(candidate)
            continue
        scored = [(float(scores.get(symbol, float("-inf"))), i) for i, symbol in enumerate(picks)]
        weakest_score, weakest_i = min(scored)
        candidate_score = float(scores.get(candidate, float("-inf")))
        if candidate_score - weakest_score > hurdle_points:
            picks[weakest_i] = candidate

    rank_order = {symbol: i for i, symbol in enumerate(ranked)}
    return sorted(picks[:top_n], key=lambda symbol: rank_order[symbol])
