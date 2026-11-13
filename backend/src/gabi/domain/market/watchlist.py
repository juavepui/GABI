"""Empresas seguidas (#182): the note rules and each row of the view, from values already read in batch.

Nothing here reads data: the use case passes the saved rows, the frozen ranking table and the journal
counts. A change since the company was added is only given when both scores come from the same model.
"""

import math

import pandas as pd

MAX_COMPANIES = 50
MAX_NOTE = 500


def clean_note(note: str | None) -> str | None:
    text = (note or "").strip()
    if len(text) > MAX_NOTE:
        raise ValueError(f"La nota admite como máximo {MAX_NOTE} caracteres.")
    return text or None


def _number(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _text(value) -> str | None:
    return None if value is None or value != value else str(value)


def standing(table: pd.DataFrame, symbol: str) -> tuple[float | None, int | None]:
    """Score and global position (1 = best, before filters) in the ranking table, sorted by score."""
    if symbol not in table.index:
        return None, None
    return _number(table.at[symbol, "composite_score"]), int(table.index.get_loc(symbol)) + 1


def rows(saved: list[dict], table: pd.DataFrame | None, model_id: str, theses: dict[str, dict]) -> list[dict]:
    """The view's rows in the order they were added; `table=None` while there is no ranking."""
    result = []
    for item in saved:
        symbol = item["symbol"]
        listed = table is not None and symbol in table.index
        row = table.loc[symbol] if listed and table is not None else {}
        score, rank = standing(table, symbol) if listed else (None, None)
        comparable = item.get("model_id") == model_id
        added_score, added_rank = _number(item.get("score_at_add")), item.get("rank_at_add")
        journal = theses.get(symbol) or {}
        earnings = _text(row.get("next_earnings_date"))
        result.append({
            "symbol": symbol, "added_at": item["added_at"], "note": item.get("note"),
            "name": _text(row.get("name")), "sector": _text(row.get("sector")), "in_ranking": listed,
            "composite_score": score, "rank": rank,
            "score_at_add": added_score, "rank_at_add": added_rank, "same_model": comparable,
            "score_change": score - added_score if comparable and score is not None and added_score is not None
            else None,
            # Positive when the company climbed: from position 12 to 5 is +7.
            "rank_change": added_rank - rank if comparable and rank is not None and added_rank is not None
            else None,
            "next_earnings_date": earnings[:10] if earnings else None,
            "next_earnings_is_estimate": _number(row.get("next_earnings_is_estimate")) == 1 if earnings else None,
            "open_theses": int(journal.get("open", 0)), "theses": int(journal.get("total", 0)),
        })
    return result
