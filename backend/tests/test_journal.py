import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gabi import journal


def test_expected_value_basic():
    ev = journal.compute_expected_value(
        entry_price=100,
        bear_price=80, base_price=110, bull_price=150,
        bear_prob=20, base_prob=50, bull_prob=30,
    )
    assert ev is not None
    assert round(ev["expected_price"], 2) == round(0.2 * 80 + 0.5 * 110 + 0.3 * 150, 2)
    assert ev["probs_summed_to_100"] is True


def test_expected_value_normalizes_probabilities_not_summing_100():
    ev = journal.compute_expected_value(
        entry_price=100,
        bear_price=80, base_price=100, bull_price=120,
        bear_prob=10, base_prob=10, bull_prob=10,  # suman 30, no 100
    )
    assert ev is not None
    assert ev["probs_summed_to_100"] is False
    # Normalizado, cada escenario pesa 1/3 -> precio esperado = media simple.
    assert round(ev["expected_price"], 2) == 100.0


def test_expected_value_returns_none_with_missing_data():
    assert journal.compute_expected_value(100, None, 100, 120, 20, 50, 30) is None
    assert journal.compute_expected_value(0, 80, 100, 120, 20, 50, 30) is None
    assert journal.compute_expected_value(100, 80, 100, 120, 0, 0, 0) is None


def test_add_list_review_delete_entry_roundtrip(tmp_path, monkeypatch):
    from gabi import config

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test_gabi.db")

    journal.init_db()
    entry_id = journal.add_entry({
        "symbol": "AAPL",
        "created_at": "2026-09-16",
        "horizon": "Medio (6-12 meses)",
        "entry_price": 230.0,
        "thesis": "Ecosistema fuerte, servicios en crecimiento.",
        "bear_price": 200.0, "base_price": 250.0, "bull_price": 300.0,
        "bear_prob": 20, "base_prob": 50, "bull_prob": 30,
        "catalysts": "Nuevo ciclo de iPhone",
        "risks": "Desaceleración en China",
        "position_size_pct": 5,
        "notes": "",
    })
    assert entry_id is not None

    entries = journal.list_entries()
    assert len(entries) == 1
    assert entries.iloc[0]["symbol"] == "AAPL"
    assert entries.iloc[0]["status"] == "abierta"

    journal.update_review(entry_id, "2027-03-16", 260.0, "Subió tras buenos resultados de servicios.")
    entries = journal.list_entries()
    assert entries.iloc[0]["status"] == "revisada"
    assert entries.iloc[0]["review_price"] == 260.0

    journal.delete_entry(entry_id)
    assert journal.list_entries().empty
