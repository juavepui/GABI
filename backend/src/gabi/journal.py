"""Diario de inversión: tesis por empresa (precio de entrada, escenarios de
valoración, catalizadores, riesgos) y su revisión posterior.

La idea (inspirada en la disciplina de escribir la tesis *antes* de invertir
y revisarla meses después) es que se aprende mucho más entendiendo por qué
una inversión salió bien o mal que acumulando indicadores."""
import pandas as pd

from gabi.domain.portfolio.journal import compute_expected_value as _compute_expected_value

from .storage import get_connection

SCHEMA = """
CREATE TABLE IF NOT EXISTS journal_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    created_at TEXT NOT NULL,
    horizon TEXT,
    entry_price REAL,
    thesis TEXT,
    bear_price REAL, base_price REAL, bull_price REAL,
    bear_prob REAL, base_prob REAL, bull_prob REAL,
    catalysts TEXT,
    risks TEXT,
    position_size_pct REAL,
    notes TEXT,
    status TEXT NOT NULL DEFAULT 'abierta',
    review_date TEXT,
    review_price REAL,
    review_notes TEXT
);
"""


def init_db():
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        conn.commit()


def add_entry(data: dict) -> int:
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        cur = conn.execute(
            "INSERT INTO journal_entries "
            "(symbol, created_at, horizon, entry_price, thesis, bear_price, base_price, bull_price, "
            "bear_prob, base_prob, bull_prob, catalysts, risks, position_size_pct, notes, status) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                data["symbol"], data["created_at"], data.get("horizon"), data.get("entry_price"),
                data.get("thesis"), data.get("bear_price"), data.get("base_price"), data.get("bull_price"),
                data.get("bear_prob"), data.get("base_prob"), data.get("bull_prob"),
                data.get("catalysts"), data.get("risks"), data.get("position_size_pct"),
                data.get("notes"), "abierta",
            ),
        )
        conn.commit()
        return cur.lastrowid


def list_entries() -> pd.DataFrame:
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        return pd.read_sql_query("SELECT * FROM journal_entries ORDER BY created_at DESC, id DESC", conn)


def update_review(entry_id: int, review_date: str, review_price, review_notes: str, status: str = "revisada"):
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        conn.execute(
            "UPDATE journal_entries SET review_date=?, review_price=?, review_notes=?, status=? WHERE id=?",
            (review_date, review_price, review_notes, status, entry_id),
        )
        conn.commit()


def delete_entry(entry_id: int):
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        conn.execute("DELETE FROM journal_entries WHERE id=?", (entry_id,))
        conn.commit()


def compute_expected_value(entry_price, bear_price, base_price, bull_price, bear_prob, base_prob, bull_prob):
    return _compute_expected_value(entry_price, bear_price, base_price, bull_price,
                                   bear_prob, base_prob, bull_prob)
