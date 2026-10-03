from gabi.domain.portfolio import journal


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
