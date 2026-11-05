"""Semáforo del mercado (#308): cómo está la bolsa hoy, en palabras, con 4 comprobaciones de umbrales fijos.

Es **contexto, no señal**: no cambia la puntuación ni el ranking, no recomienda comprar ni vender y no está
demostrado que acierte el momento. Versión de las reglas: ``MARKET_HEALTH_VERSION``; cambiar un umbral es una
versión nueva.

Comprobaciones (cada una: pasa / precaución / falla; sin dato, no cuenta):

1. Tendencia: el índice (el ETF del S&P 500 que GABI usa de referencia) frente a sus medias de 50 y 200 sesiones.
   Pasa por encima de las dos; falla por debajo de las dos; precaución en medio.
2. Participación: % de empresas del universo cuyo precio está por encima de su media de 200 sesiones.
   Pasa desde el 60 %; falla por debajo del 40 %.
3. Jornadas de ventas fuertes en las últimas 25 sesiones: el índice cae al menos un 0,2 % con más volumen que la
   sesión anterior. Pasa con 3 o menos; falla con 6 o más.
4. Nerviosismo: el VIX (FRED ``VIXCLS``). Pasa por debajo de 20 si no está más de un 15 % por encima de su media de
   20 sesiones; falla desde 30; precaución en medio o con ese salto.

Nota: pasa = 2 puntos, precaución = 1, falla = 0; la nota es el % de los puntos posibles con las comprobaciones que
tienen dato. Estado: «Favorable» desde 75, «Con presión» desde 40 y «En corrección» por debajo. Si la tendencia
falla, el estado no puede ser «Favorable».
"""

import math

import pandas as pd

MARKET_HEALTH_VERSION = "market-health-v1"
SMA_SHORT, SMA_LONG = 50, 200
BREADTH_PASS, BREADTH_FAIL = 60.0, 40.0
DISTRIBUTION_WINDOW, DISTRIBUTION_DROP = 25, -0.002
DISTRIBUTION_PASS, DISTRIBUTION_FAIL = 3, 6
VIX_CALM, VIX_FEAR, VIX_SMA, VIX_JUMP = 20.0, 30.0, 20, 0.15
HIGH_WINDOW = 252
FAVORABLE, PRESSURE = 75.0, 40.0
HISTORY_SESSIONS = 120  # How far back «días en el estado» is counted.
POINTS = {"pass": 2, "caution": 1, "fail": 0}
STATES = {"favorable": "Favorable", "pressure": "Con presión", "correction": "En corrección"}


def _finite(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _close(frame: pd.DataFrame) -> pd.Series:
    """Adjusted close when complete, else close: the same rule as the technical metrics."""
    column = "adj_close" if "adj_close" in frame and frame["adj_close"].notna().all() else "close"
    return frame[column].astype(float)


def index_series(index: pd.DataFrame) -> pd.DataFrame:
    """Per session of the index: close, its 50/200 averages and whether it was a heavy-selling day."""
    close = _close(index)
    change = close.pct_change()
    volume = index["volume"].astype(float) if "volume" in index else pd.Series(float("nan"), index=index.index)
    heavy = (change <= DISTRIBUTION_DROP) & (volume > volume.shift(1))
    return pd.DataFrame({
        "close": close, "sma50": close.rolling(SMA_SHORT, min_periods=SMA_SHORT).mean(),
        "sma200": close.rolling(SMA_LONG, min_periods=SMA_LONG).mean(),
        "heavy": heavy, "heavy_25": heavy.astype(int).rolling(DISTRIBUTION_WINDOW, min_periods=DISTRIBUTION_WINDOW).sum(),
    })


def breadth_series(closes: pd.DataFrame) -> pd.DataFrame:
    """Per session: % of companies above their 200 and 50-session averages and how many made a one-year high.

    `closes`: one column per company (adjusted closes), sessions as rows. Only companies with enough history
    for each average count in its denominator."""
    sma200 = closes.rolling(SMA_LONG, min_periods=SMA_LONG).mean()
    sma50 = closes.rolling(SMA_SHORT, min_periods=SMA_SHORT).mean()
    high = closes.rolling(HIGH_WINDOW, min_periods=HIGH_WINDOW).max()
    counted200, counted50 = sma200.notna().sum(axis=1), sma50.notna().sum(axis=1)
    return pd.DataFrame({
        "above200": 100 * (closes > sma200).sum(axis=1) / counted200.where(counted200 > 0),
        "above50": 100 * (closes > sma50).sum(axis=1) / counted50.where(counted50 > 0),
        "counted": counted200, "new_highs": ((closes >= high) & high.notna()).sum(axis=1),
    })


def trend_check(close, sma50, sma200) -> str | None:
    close, sma50, sma200 = _finite(close), _finite(sma50), _finite(sma200)
    if close is None or sma50 is None or sma200 is None:
        return None
    above = (close > sma50) + (close > sma200)
    return "pass" if above == 2 else "fail" if above == 0 else "caution"


def breadth_check(above200) -> str | None:
    value = _finite(above200)
    if value is None:
        return None
    return "pass" if value >= BREADTH_PASS else "fail" if value < BREADTH_FAIL else "caution"


def distribution_check(heavy_days) -> str | None:
    value = _finite(heavy_days)
    if value is None:
        return None
    return "pass" if value <= DISTRIBUTION_PASS else "fail" if value >= DISTRIBUTION_FAIL else "caution"


def vix_check(vix, vix_sma) -> str | None:
    vix, vix_sma = _finite(vix), _finite(vix_sma)
    if vix is None:
        return None
    if vix >= VIX_FEAR:
        return "fail"
    jump = vix_sma is not None and vix > vix_sma * (1 + VIX_JUMP)
    return "caution" if vix >= VIX_CALM or jump else "pass"


def rate(checks: dict[str, str | None]) -> tuple[float | None, str | None]:
    """The 0-100 note and the state from the checks with data."""
    known = [result for result in checks.values() if result is not None]
    if not known:
        return None, None
    score = 100 * sum(POINTS[result] for result in known) / (2 * len(known))
    state = "favorable" if score >= FAVORABLE else "pressure" if score >= PRESSURE else "correction"
    if state == "favorable" and checks.get("trend") == "fail":
        state = "pressure"
    return score, state


def _days(states: pd.Series) -> tuple[int, bool]:
    """Consecutive sessions, ending today, in today's state; True when it fills the whole window counted."""
    states = states.dropna()
    if states.empty:
        return 0, False
    last, count = states.iloc[-1], 0
    for value in reversed(states.tolist()):
        if value != last:
            return count, False
        count += 1
    return count, True


def evaluate(index: pd.DataFrame, closes: pd.DataFrame, vix: pd.Series | None) -> dict:
    """The traffic light for the index's last session, from data already read.

    `index`: the benchmark's prices (close, adj_close, volume) by date; `closes`: universe adjusted closes;
    `vix`: VIXCLS by date (may be empty)."""
    if index is None or index.empty or len(index) < SMA_LONG + 1:
        return {"status": "no_data", "version": MARKET_HEALTH_VERSION, "sessions": 0 if index is None else len(index)}
    trend = index_series(index)
    breadth = breadth_series(closes.reindex(trend.index)) if not closes.empty else pd.DataFrame(index=trend.index)
    vix = (vix if vix is not None else pd.Series(dtype=float)).astype(float).sort_index()
    vix_sma = vix.rolling(VIX_SMA, min_periods=VIX_SMA).mean()
    # FRED publishes the VIX a day late at most; carry its last value a few sessions, never further.
    vix_today = vix.reindex(trend.index, method="ffill", limit=5) if not vix.empty else pd.Series(index=trend.index)
    vix_sma_today = (vix_sma.reindex(trend.index, method="ffill", limit=5) if not vix.empty
                     else pd.Series(index=trend.index))

    def checks_at(day) -> dict[str, str | None]:
        return {"trend": trend_check(*trend.loc[day, ["close", "sma50", "sma200"]]),
                "breadth": breadth_check(breadth["above200"].get(day) if "above200" in breadth else None),
                "distribution": distribution_check(trend.at[day, "heavy_25"]),
                "volatility": vix_check(vix_today.get(day), vix_sma_today.get(day))}

    window = trend.index[-HISTORY_SESSIONS:]
    states = pd.Series({day: rate(checks_at(day))[1] for day in window})
    today = trend.index[-1]
    checks = checks_at(today)
    score, state = rate(checks)
    days, at_least = _days(states)
    last_vix = vix.dropna()

    def value(frame: pd.DataFrame, column: str):
        return _finite(frame[column].get(today)) if column in frame else None

    return {
        "status": "ready", "version": MARKET_HEALTH_VERSION, "as_of": today.date().isoformat(),
        "score": score, "state": state, "state_label": None if state is None else STATES[state],
        "days_in_state": days, "days_at_least": at_least, "history_sessions": len(window),
        "checks": [describe(check) for check in [
            {"key": "trend", "result": checks["trend"],
             "values": {"close": value(trend, "close"), "sma50": value(trend, "sma50"),
                        "sma200": value(trend, "sma200")}},
            {"key": "breadth", "result": checks["breadth"],
             "values": {"above200": value(breadth, "above200"), "above50": value(breadth, "above50"),
                        "new_highs": value(breadth, "new_highs"), "counted": value(breadth, "counted")}},
            {"key": "distribution", "result": checks["distribution"],
             "values": {"heavy_days": value(trend, "heavy_25"), "window": DISTRIBUTION_WINDOW}},
            {"key": "volatility", "result": checks["volatility"],
             "values": {"vix": _finite(vix_today.get(today)), "vix_sma20": _finite(vix_sma_today.get(today)),
                        "vix_date": None if last_vix.empty else pd.Timestamp(last_vix.index[-1]).date().isoformat()}},
        ]],
    }


def _number(value: float, digits: int = 1) -> str:
    return f"{value:.{digits}f}".replace(".", ",")


TITLES = {"trend": "Tendencia del índice", "breadth": "Participación", "distribution": "Jornadas de ventas fuertes",
          "volatility": "Nerviosismo (VIX)"}


def describe(check: dict) -> dict:
    """The check with its title and one plain sentence; every number comes from its `values`."""
    key, result, values = check["key"], check["result"], check["values"]
    text = "Sin datos suficientes en tu equipo para esta comprobación."
    if key == "trend" and result is not None:
        above50, above200 = values["close"] > values["sma50"], values["close"] > values["sma200"]
        text = ("El S&P 500 está por encima de sus medias de 50 y 200 sesiones." if above50 and above200
                else "El S&P 500 está por debajo de sus medias de 50 y 200 sesiones." if not above50 and not above200
                else "El S&P 500 está por encima de su media de 200 sesiones y por debajo de la de 50." if above200
                else "El S&P 500 está por debajo de su media de 200 sesiones y por encima de la de 50.")
    elif key == "breadth" and result is not None:
        text = (f"El {_number(values['above200'])} % de las empresas está por encima de su media de 200 sesiones"
                + (f" y el {_number(values['above50'])} %, por encima de la de 50" if values["above50"] is not None
                   else "")
                + (f"; {int(values['new_highs'])} marcan máximos de un año." if values["new_highs"] is not None
                   else "."))
    elif key == "distribution" and result is not None:
        days = int(values["heavy_days"])
        text = (f"{days} {'jornada' if days == 1 else 'jornadas'} de ventas fuertes en las últimas "
                f"{values['window']} sesiones.")
    elif key == "volatility":
        text = ("Sin dato del VIX: llega con los datos de FRED en la próxima actualización." if result is None
                else f"El VIX está en {_number(values['vix'])}"
                + (f" (su media de 20 sesiones: {_number(values['vix_sma20'])})." if values["vix_sma20"] is not None
                   else "."))
    return {**check, "title": TITLES[key], "text": text}
