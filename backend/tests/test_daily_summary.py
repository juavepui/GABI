"""«Tu resumen de hoy» (#307): plain-language sentences from templates, every number traceable to its input."""

import re
from datetime import date

from gabi.domain.portfolio import daily_summary as summary

TODAY = date(2026, 11, 5)  # Thursday.
MODEL = "GABI-MF-v3"


def _row(symbol: str, *, score=None, before=None, rank=None, rank_before=None, same_model=True) -> dict:
    return {"symbol": symbol, "added_at": "2026-10-01T10:00:00", "composite_score": score, "score_at_add": before,
            "score_change": score - before if same_model and score is not None and before is not None else None,
            "rank": rank, "rank_at_add": rank_before,
            "rank_change": rank_before - rank if same_model and rank is not None and rank_before is not None
            else None, "same_model": same_model}


def _tokens(value) -> set[str]:
    """Every way the summary may write a value: decimal, integer, day and month."""
    if isinstance(value, dict):
        return set().union(*(_tokens(item) for item in value.values())) if value else set()
    if isinstance(value, list):
        return set().union(*(_tokens(item) for item in value)) if value else set()
    if isinstance(value, bool) or value is None:
        return set()
    if isinstance(value, int | float):
        tokens = {summary.number(value), summary.number(value, 0), str(abs(int(value)))}
        return tokens
    if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", value):
        return set(re.findall(r"\d+", summary.long_day(value)))
    return set()


def _numbers_come_from_values(sentence: dict) -> None:
    text = sentence["text"]
    for symbol in sentence["symbols"] + list(sentence["values"].get("symbols", [])):
        text = text.replace(symbol, "")
    text = text.replace(MODEL, "")
    allowed = _tokens(sentence["values"])
    for found in re.findall(r"\d+(?:,\d+)?", text):
        assert found in allowed, (found, sentence)


def _build(watched, held=(), target=(), scored=None, earnings=None, latest="2026-11-04"):
    mine = [row["symbol"] for row in watched] + list(held)
    return summary.build(watched=watched, held=list(held), target=list(target),
                         scored=set(mine) if scored is None else scored, earnings=earnings or {},
                         latest_price_date=latest, target_size=20, today=TODAY, model_id=MODEL)


def test_without_companies_says_so_and_has_no_sentences():
    result = _build([])
    assert result["status"] == "no_companies" and result["sentences"] == [] and result["followed_count"] == 0


def test_big_moves_are_named_with_their_numbers_and_small_ones_are_not():
    watched = [_row("AAA", score=67.3, before=55.0, rank=12, rank_before=20),  # +12,3 points.
               _row("BBB", score=50.0, before=48.0, rank=10, rank_before=4),  # Score small, falls 6 places.
               _row("CCC", score=40.0, before=41.0, rank=30, rank_before=31)]  # Noise.
    result = _build(watched, target=["AAA"])
    texts = {sentence["kind"]: sentence for sentence in result["sentences"]}
    moves = texts["moves"]
    assert moves["text"] == ("Desde que empezaste a seguirlas, 2 de las empresas que sigues han cambiado mucho: "
                             "AAA sube 12,3 puntos (de 55,0 a 67,3) y BBB baja 6 puestos (del 4 al 10).")
    assert moves["symbols"] == ["AAA", "BBB"] and moves["tone"] == "neutral"
    assert texts["data"]["text"] == "Datos con los precios del cierre del miércoles 4 nov."
    assert texts["target"]["text"] == ("1 de tus 3 empresas está hoy en la cartera objetivo de GABI "
                                       "(las 20 con más puntuación): AAA.")
    for sentence in result["sentences"]:
        _numbers_come_from_values(sentence)


def test_nothing_changed_is_said_in_words():
    watched = [_row(symbol, score=50.0, before=49.0, rank=10 + index, rank_before=11 + index)
               for index, symbol in enumerate(["AAA", "BBB"])]
    result = _build(watched)
    texts = {sentence["kind"]: sentence["text"] for sentence in result["sentences"]}
    assert texts["moves"] == ("Ninguna de las 2 empresas que sigues ha cambiado mucho desde que empezaste a "
                              "seguirlas: menos de 10 puntos y de 5 puestos.")
    assert texts["target"] == "Ninguna de tus 2 empresas está hoy en la cartera objetivo de GABI (las 20 con más puntuación)."
    assert "earnings" not in texts
    for sentence in result["sentences"]:
        _numbers_come_from_values(sentence)


def test_other_model_unscored_held_and_results_this_week():
    watched = [_row("OLD", score=60.0, before=30.0, rank=5, rank_before=50, same_model=False),
               _row("GONE", before=50.0, rank_before=10)]
    earnings = {"OLD": ("2026-11-06", False), "HELD": ("2026-11-12", True), "GONE": ("2026-11-20", False)}
    result = _build(watched, held=["HELD", "OLD"], target=["HELD"], scored={"OLD", "HELD"}, earnings=earnings)
    assert result["followed_count"] == 3 and result["held_count"] == 2 and result["watched_count"] == 2
    texts = {sentence["kind"]: sentence for sentence in result["sentences"]}
    assert "moves" not in texts  # OLD is from another model; GONE has no score today.
    assert texts["other_model"]["text"].startswith("OLD no se puede comparar")
    assert MODEL in texts["other_model"]["text"]
    assert texts["unscored"]["text"] == "GONE no tiene puntuación hoy: faltan datos de sus precios o sus cuentas."
    assert texts["earnings"]["text"] == ("2 empresas de las tuyas presentan resultados en los próximos 7 días: "
                                         "OLD (6 nov) y HELD (12 nov, fecha estimada).")
    assert texts["earnings"]["values"]["estimated"] == ["HELD"]
    for sentence in result["sentences"]:
        _numbers_come_from_values(sentence)


def test_long_lists_are_cut_and_the_rest_counted():
    watched = [_row(f"S{chr(65 + index)}", score=80.0 + index, before=50.0, rank=1 + index, rank_before=40)
               for index in range(5)]
    result = _build(watched, latest=None)
    moves = next(sentence for sentence in result["sentences"] if sentence["kind"] == "moves")
    assert moves["text"].endswith(" y 2 más.") and moves["tone"] == "good"
    assert moves["values"]["not_named"] == 2
    assert all(sentence["kind"] != "data" for sentence in result["sentences"])
    for sentence in result["sentences"]:
        _numbers_come_from_values(sentence)
