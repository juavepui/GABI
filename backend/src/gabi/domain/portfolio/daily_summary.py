"""«Tu resumen de hoy» (#307): unas pocas frases en lenguaje llano, hechas con plantillas fijas y sin IA.

«Tus empresas» son las que sigues y las de Mi cartera. Cada frase lleva en ``values`` los datos de los
que sale: todo número del texto es uno de esos valores formateado aquí (regla de determinismo, #296).

GABI no guarda una foto diaria de la puntuación de cada empresa, así que «qué ha cambiado» se mide
contra el día en que empezaste a seguirla (puntuación y puesto guardados entonces) y solo si las dos
puntuaciones son del mismo modelo. Los umbrales son los de los avisos de cambios del ranking.
"""

from datetime import date, datetime

from gabi.domain.market.signals import DEFAULT_THRESHOLDS
from gabi.domain.portfolio.alerts import WINDOW_DAYS

SCORE_POINTS = float(DEFAULT_THRESHOLDS["score_change"])
RANK_PLACES = int(DEFAULT_THRESHOLDS["rank_change"])
MAX_NAMED = 3
MONTHS = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")
MARKET_TONE = {"favorable": "good", "pressure": "neutral", "correction": "bad"}
WEEKDAYS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


def number(value: float, digits: int = 1) -> str:
    """Spanish decimal comma, no sign: «12,3»."""
    return f"{abs(value):.{digits}f}".replace(".", ",")


def short_day(value: date | str) -> str:
    """«6 nov»."""
    day = _date(value)
    return f"{day.day} {MONTHS[day.month - 1]}"


def long_day(value: date | str) -> str:
    """«martes 4 nov»."""
    day = _date(value)
    return f"{WEEKDAYS[day.weekday()]} {short_day(day)}"


def _date(value: date | str) -> date:
    if isinstance(value, datetime):
        return value.date()
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


def _join(items: list[str]) -> str:
    """«A», «A y B», «A, B y C»; beyond MAX_NAMED, «A, B, C y 2 más»."""
    shown, rest = items[:MAX_NAMED], len(items) - MAX_NAMED
    if rest > 0:
        return ", ".join(shown) + f" y {rest} más"
    return shown[0] if len(shown) == 1 else ", ".join(shown[:-1]) + " y " + shown[-1]


def _companies(count: int) -> str:
    return "1 empresa" if count == 1 else f"{count} empresas"


def _sentence(kind: str, tone: str, text: str, values: dict, symbols: list[str] | None = None,
              link: str | None = None) -> dict:
    symbols = symbols or []
    if len(symbols) > MAX_NAMED:  # «y 2 más» in the text.
        values = {**values, "not_named": len(symbols) - MAX_NAMED}
    return {"kind": kind, "tone": tone, "text": text, "symbols": symbols, "link": link, "values": values}


def _move(row: dict) -> str:
    """How a company moved since it was followed: the score when it crossed the threshold, else the rank."""
    symbol, change = row["symbol"], row["score_change"]
    if change is not None and abs(change) >= SCORE_POINTS:
        verb = "sube" if change > 0 else "baja"
        return (f"{symbol} {verb} {number(change)} puntos (de {number(row['score_at_add'])} "
                f"a {number(row['composite_score'])})")
    places = row["rank_change"]  # Positive when it climbed.
    verb = "sube" if places > 0 else "baja"
    return f"{symbol} {verb} {abs(places)} puestos (del {row['rank_at_add']} al {row['rank']})"


def _moved(row: dict) -> bool:
    score, places = row.get("score_change"), row.get("rank_change")
    return (score is not None and abs(score) >= SCORE_POINTS) or (places is not None and abs(places) >= RANK_PLACES)


def _climbed(row: dict) -> bool:
    """The direction _move describes: the score's when it crossed the threshold, else the rank's."""
    change = row["score_change"]
    if change is not None and abs(change) >= SCORE_POINTS:
        return change > 0
    return row["rank_change"] > 0


def build(*, watched: list[dict], held: list[str], target: list[str], scored: set[str],
          earnings: dict[str, tuple[str | None, bool]], latest_price_date: str | None, target_size: int,
          today: date, model_id: str, market: dict | None = None) -> dict:
    """The summary from values already read once.

    `watched`: rows of «Empresas seguidas» (`domain.market.watchlist.rows`); `held`: Mi cartera's symbols;
    `target`: today's frozen target; `scored`: the companies with a score today;
    `earnings`: symbol → (next results date, estimated?); `market`: the traffic light (#308), when computed.
    """
    watched_symbols = [row["symbol"] for row in watched]
    mine = list(dict.fromkeys([*watched_symbols, *held]))
    base = {"followed_count": len(mine), "watched_count": len(watched_symbols), "held_count": len(held),
            "score_points": SCORE_POINTS, "rank_places": RANK_PLACES, "window_days": WINDOW_DAYS}
    if not mine:
        return {**base, "status": "no_companies", "sentences": []}
    sentences = []
    if latest_price_date:
        sentences.append(_sentence(
            "data", "neutral", f"Datos con los precios del cierre del {long_day(latest_price_date)}.",
            {"latest_price_date": latest_price_date}))

    if watched:
        comparable = [row for row in watched if row.get("same_model")
                      and (row.get("score_change") is not None or row.get("rank_change") is not None)]
        movers = sorted((row for row in comparable if _moved(row)),
                        key=lambda row: (-abs(row["score_change"] or 0), -abs(row["rank_change"] or 0), row["symbol"]))
        values = {"compared": len(comparable), "moved": len(movers), "score_points": SCORE_POINTS,
                  "rank_places": RANK_PLACES,
                  "companies": {row["symbol"]: {key: row.get(key) for key in (
                      "added_at", "score_at_add", "composite_score", "score_change", "rank_at_add", "rank",
                      "rank_change")} for row in movers}}
        if movers:
            up = sum(1 for row in movers if _climbed(row))
            tone = "good" if up == len(movers) else "bad" if up == 0 else "neutral"
            subject = ("1 de las empresas que sigues ha cambiado mucho" if len(movers) == 1
                       else f"{len(movers)} de las empresas que sigues han cambiado mucho")
            sentences.append(_sentence(
                "moves", tone, f"Desde que empezaste a seguirlas, {subject}: "
                f"{_join([_move(row) for row in movers])}.", values, [row["symbol"] for row in movers],
                "/descubrir/seguidas"))
        elif comparable:
            subject = ("La empresa que sigues no ha cambiado mucho" if len(comparable) == 1
                       else f"Ninguna de las {len(comparable)} empresas que sigues ha cambiado mucho")
            sentences.append(_sentence(
                "moves", "neutral", f"{subject} desde que empezaste a seguirla{'s' if len(comparable) > 1 else ''}: "
                f"menos de {number(SCORE_POINTS, 0)} puntos y de {RANK_PLACES} puestos.", values,
                link="/descubrir/seguidas"))
        other_model = [row["symbol"] for row in watched if not row.get("same_model")]
        if other_model:
            sentences.append(_sentence(
                "other_model", "neutral",
                f"{_join(other_model)} no se {'puede' if len(other_model) == 1 else 'pueden'} comparar con el día "
                f"en que {'la' if len(other_model) == 1 else 'las'} empezaste a seguir: entonces GABI puntuaba "
                f"con otro modelo y hoy usa {model_id}.",
                {"symbols": other_model, "model_id": model_id}, other_model, "/descubrir/seguidas"))

    unscored = [symbol for symbol in mine if symbol not in scored]
    if unscored:
        sentences.append(_sentence(
            "unscored", "bad", f"{_join(unscored)} no {'tiene' if len(unscored) == 1 else 'tienen'} puntuación hoy: "
            "faltan datos de sus precios o sus cuentas.", {"symbols": unscored}, unscored))

    chosen = [symbol for symbol in mine if symbol in set(target)]
    values = {"in_target": len(chosen), "followed_count": len(mine), "target_size": target_size}
    if chosen:
        sentences.append(_sentence(
            "target", "good", f"{len(chosen)} de tus {_companies(len(mine))} "
            f"{'está' if len(chosen) == 1 else 'están'} hoy en la cartera objetivo de GABI "
            f"(las {target_size} con más puntuación): {_join(chosen)}.", values, chosen, "/cartera"))
    else:
        sentences.append(_sentence(
            "target", "neutral", f"{'Tu empresa no está' if len(mine) == 1 else 'Ninguna de tus ' + _companies(len(mine)) + ' está'} "
            f"hoy en la cartera objetivo de GABI (las {target_size} con más puntuación).", values, link="/cartera"))

    soon = sorted((when.isoformat(), symbol, estimated) for symbol in mine if symbol in earnings
                  for raw, estimated in [earnings[symbol]] if raw
                  for when in [_date(raw)] if 0 <= (when - today).days <= WINDOW_DAYS)
    if soon:
        parts = [f"{symbol} ({short_day(day)}{', fecha estimada' if estimated else ''})" for day, symbol, estimated in soon]
        sentences.append(_sentence(
            "earnings", "neutral", f"{_companies(len(soon)).capitalize()} de las tuyas "
            f"{'presenta' if len(soon) == 1 else 'presentan'} resultados en los próximos {WINDOW_DAYS} días: "
            f"{_join(parts)}.", {"count": len(soon), "window_days": WINDOW_DAYS,
                                 "dates": {symbol: day for day, symbol, _ in soon},
                                 "estimated": [symbol for _, symbol, estimated in soon if estimated]},
            [symbol for _, symbol, _ in soon], "/eventos"))
    if market and market.get("status") == "ready" and market.get("state"):
        days = int(market["days_in_state"])
        since = (f"desde hace {'al menos ' if market.get('days_at_least') else ''}"
                 f"{days} {'sesión' if days == 1 else 'sesiones'}")
        sentences.append(_sentence(
            "market", MARKET_TONE[market["state"]],
            f"El mercado está «{market['state_label']}» {since} (nota de {number(market['score'], 0)} sobre 100): "
            "describe el momento, no lo que hará.",
            {"score": market["score"], "scale": 100, "days_in_state": days, "state": market["state"]}))
    return {**base, "status": "ready", "sentences": sentences}
