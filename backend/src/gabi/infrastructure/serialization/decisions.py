"""JSON serialization of the experimental decision policy and optimizer."""

import json
from dataclasses import asdict

import pandas as pd

import gabi.domain.portfolio.decisions as decision_engine


def build_decisions(table: pd.DataFrame, histories: dict[str, pd.DataFrame],
                    holdings: dict[str, float], options: dict, as_of: str) -> dict:
    policy = decision_engine.Policy(**options)
    plan = decision_engine.build_plan(table, histories, holdings, policy, as_of=as_of)
    # DataFrame JSON handles numpy scalars and missing scores without NaN on the wire.
    decisions = json.loads(plan["decisions"].to_json(orient="records"))
    risk = json.loads(pd.Series(plan["risk"], dtype=object).to_json()) if plan["risk"] else {}
    return {"decisions": decisions, "targets": plan["targets"], "rejections": plan["rejections"],
            "method": plan["method"], "risk": risk, "cash_target_pct": plan["cash_target_pct"],
            "policy": asdict(policy), "holdings": holdings, "status": "EXPERIMENTAL"}
