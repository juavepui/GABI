"""#45: French CSV parsing and the mix weights."""

import pandas as pd

from gabi import factor_history as fh

SAMPLE = """This file was created by CMPT_ME_BEME_RETS using the 202607 CRSP database.

  Value Weight Returns -- Monthly
,Lo 20,Qnt 2,Hi 20
196307,  1.00,  2.00, -3.00
196308,  0.50,  0.40,  0.30

  Equal Weight Returns -- Monthly
,Lo 20,Qnt 2,Hi 20
196307,  9.00,  9.00,  9.00
"""


def test_first_monthly_table_stops_before_the_next_table():
    table = fh._first_monthly_table(SAMPLE)
    assert list(table.columns) == ["Lo 20", "Qnt 2", "Hi 20"] and len(table) == 2
    assert table.loc["1963-07-01", "Hi 20"] == -0.03


def test_mix_uses_gabi_weights_and_rescales_without_the_risk_factor():
    frame = pd.DataFrame({"HML": [0.01], "RMW": [0.02], "MOM": [0.03], "RISK": [0.04]})
    assert abs(fh.mix(frame).iloc[0] - (0.3 * 0.01 + 0.35 * 0.02 + 0.25 * 0.03 + 0.1 * 0.04)) < 1e-12
    assert abs(fh.mix(frame.drop(columns="RISK")).iloc[0] - (0.3 * 0.01 + 0.35 * 0.02 + 0.25 * 0.03) / 0.9) < 1e-12
    assert fh.SPEC["weights_match_scoring_default"]
