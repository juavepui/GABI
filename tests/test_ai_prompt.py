import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gabi import ai_prompt


def _row(**overrides):
    base = {
        "name": "Acme Corp", "sector": "Information Technology",
        "composite_score": 72.3, "value_score": 60.0, "quality_score": 80.0, "momentum_score": 75.0,
        "latest_10k_url": "https://www.sec.gov/Archives/edgar/data/1/000001/acme-10k.htm",
        "latest_10k_date": "2026-02-01",
        "latest_10q_url": "https://www.sec.gov/Archives/edgar/data/1/000002/acme-10q.htm",
        "latest_10q_date": "2026-05-01",
    }
    base.update(overrides)
    return pd.Series(base)


def _breakdown():
    return pd.DataFrame([
        {"metric": "pe", "value": 22.5, "percentile": 65.0},
        {"metric": "roic", "value": 0.18, "percentile": 80.0},
        {"metric": "revenue_growth_yoy", "value": 0.12, "percentile": 70.0},
    ])


def test_prompt_includes_company_identity_and_forbids_price_prediction():
    prompt = ai_prompt.build_analysis_prompt(_row(), _breakdown(), "ACME")
    assert "Acme Corp" in prompt
    assert "ACME" in prompt
    assert "Information Technology" in prompt
    assert "va a subir" in prompt.lower()


def test_prompt_includes_scores():
    prompt = ai_prompt.build_analysis_prompt(_row(), _breakdown(), "ACME")
    assert "72.3/100" in prompt
    assert "80.0/100" in prompt  # quality_score


def test_prompt_includes_metrics_table_with_spanish_labels_not_raw_keys():
    prompt = ai_prompt.build_analysis_prompt(_row(), _breakdown(), "ACME")
    assert "PER" in prompt  # label de 'pe'
    assert "ROIC" in prompt  # label de 'roic'
    assert "65/100" in prompt  # percentil de PER


def test_prompt_includes_filing_links():
    prompt = ai_prompt.build_analysis_prompt(_row(), _breakdown(), "ACME")
    assert "acme-10k.htm" in prompt
    assert "acme-10q.htm" in prompt
    assert "2026-02-01" in prompt


def test_prompt_includes_all_ten_extraction_points():
    prompt = ai_prompt.build_analysis_prompt(_row(), _breakdown(), "ACME")
    for point in ai_prompt.EXTRACTION_POINTS:
        assert point in prompt
    assert len(ai_prompt.EXTRACTION_POINTS) == 10


def test_prompt_includes_thesis_and_invalidation_sections():
    prompt = ai_prompt.build_analysis_prompt(_row(), _breakdown(), "ACME")
    assert "Tesis alcista" in prompt
    assert "Tesis bajista" in prompt
    assert "invalidaría la inversión" in prompt


def test_prompt_forbids_ai_from_inventing_numbers():
    prompt = ai_prompt.build_analysis_prompt(_row(), _breakdown(), "ACME")
    lower = prompt.lower()
    assert "no recalcules" in lower or "no los recalcules" in lower
    assert "inventad" in lower or "inventes" in lower


def test_prompt_degrades_gracefully_without_scores_or_filings_or_metrics():
    row = pd.Series({"name": "Sin Datos SA", "sector": None})
    empty_breakdown = pd.DataFrame(columns=["metric", "value", "percentile"])
    prompt = ai_prompt.build_analysis_prompt(row, empty_breakdown, "NODATA")
    assert "no disponibles todavía" in prompt
    assert "sin métricas calculadas todavía" in prompt
    assert "sin enlaces todavía" in prompt


def test_metrics_table_skips_rows_with_nan_value():
    breakdown = pd.DataFrame([
        {"metric": "pe", "value": float("nan"), "percentile": 50.0},
        {"metric": "roic", "value": 0.15, "percentile": 60.0},
    ])
    table = ai_prompt._metrics_table(breakdown)
    assert "PER" not in table
    assert "ROIC" in table
