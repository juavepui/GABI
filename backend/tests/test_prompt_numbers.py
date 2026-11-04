"""Every number in the AI prompt comes from the code (#296): an input value formatted, or the fixed template."""

import re

import numpy as np
import pandas as pd

from gabi.application.market.prompt_text import build_analysis_prompt
from gabi.domain.market.metric_info import format_metric_value

NUMBER = re.compile(r"\d+(?:[.,]\d+)*")

ROW = pd.Series({"name": "Acme Corp", "sector": "Industrials", "composite_score": 73.456, "value_score": 61.04,
                 "quality_score": 88.95, "momentum_score": 42.5, "latest_10k_date": "2025-02-14",
                 "latest_10k_url": "https://www.sec.gov/Archives/edgar/data/320193/000032019325000008/a10k.htm",
                 "latest_10q_date": "2025-05-02", "latest_10q_url": None})
BREAKDOWN = pd.DataFrame([
    {"metric": "pe", "value": 17.3456, "percentile": 63.7},
    {"metric": "operating_margin", "value": 0.2345, "percentile": 81.2},
    {"metric": "roic", "value": 0.1789, "percentile": np.nan},
    {"metric": "momentum_12m", "value": np.nan, "percentile": 12.0},  # No value: never printed.
])


def numbers(text: str) -> set[str]:
    return set(NUMBER.findall(text))


def allowed() -> set[str]:
    """The template's own numbers plus each input exactly as the code formats it."""
    template = numbers(build_analysis_prompt(pd.Series({"name": "X", "sector": "Y"}), pd.DataFrame(), "X"))
    values = {f"{ROW[key]:.1f}" for key in ("composite_score", "value_score", "quality_score", "momentum_score")}
    for _, row in BREAKDOWN.dropna(subset=["value"]).iterrows():
        values.add(format_metric_value(row["metric"], row["value"]))
        if pd.notna(row["percentile"]):
            values.add(f"{row['percentile']:.0f}")
    values |= {ROW["latest_10k_date"], ROW["latest_10k_url"]}
    return template | {number for value in values for number in numbers(str(value))}


def test_every_number_in_the_prompt_is_an_input_or_the_template():
    prompt = build_analysis_prompt(ROW, BREAKDOWN, "ACME")
    stray = numbers(prompt) - allowed()
    assert stray == set(), f"Números que no salen de la entrada ni de la plantilla: {sorted(stray)}"
    # The inputs do appear, formatted by the code.
    assert "73.5/100" in prompt and "| 64/100 |" in prompt


def test_an_input_number_is_never_rounded_into_a_new_one():
    """A changed formatting (more decimals, another rounding) would put new numbers in the text."""
    prompt = build_analysis_prompt(ROW, BREAKDOWN, "ACME")
    assert "17.3456" not in prompt and "73.456" not in prompt


def test_the_prompt_never_asks_the_ai_to_set_thresholds():
    prompt = build_analysis_prompt(ROW, BREAKDOWN, "ACME")
    assert "fijar X e Y" not in prompt and "X%" not in prompt and "Y%" not in prompt
    assert "No propongas umbrales numéricos nuevos" in prompt
