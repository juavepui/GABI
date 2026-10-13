"""Research Lab records: the stored row of a new experiment and the decoded detail of a stored one."""

import json

import pandas as pd

from gabi.domain.research.experiments import STAGES


def require_stage(stage: str) -> None:
    if stage not in STAGES:
        raise ValueError(f"stage debe ser uno de {STAGES}.")


def record(model_id: str, stage: str, hypothesis_registered: bool, *, created_at: str, git_commit: str | None,
           deps: dict, python_version: str, env_fingerprint: str | None, weights: dict | None = None,
           returns: pd.Series | None = None, result: dict | None = None, **fields) -> dict:
    """Row for ``experiments``; returns keep only finite dated values, as published records did."""
    require_stage(stage)
    returns_json = None
    if returns is not None:
        returns_json = json.dumps({str(k): float(v) for k, v in returns.dropna().items()})
    return {"created_at": created_at, "model_id": model_id, "git_commit": git_commit,
            "weights_json": json.dumps(weights) if weights else None,
            "hypothesis_registered": int(bool(hypothesis_registered)), "stage": stage,
            "deps_json": json.dumps(deps), "python_version": python_version, "env_fingerprint": env_fingerprint,
            "returns_json": returns_json, "result_json": json.dumps(result) if result else None, **fields}


def detail(row: dict | None) -> dict:
    """Stored row plus decoded weights, result, dependencies and dated returns; {} when absent."""
    if row is None:
        return {}
    data = dict(row)
    data["weights"] = json.loads(data["weights_json"]) if data.get("weights_json") else None
    data["result"] = json.loads(data["result_json"]) if data.get("result_json") else None
    data["deps"] = json.loads(data["deps_json"]) if data.get("deps_json") else None
    if data.get("returns_json"):
        series = pd.Series(json.loads(data["returns_json"]))
        series.index = pd.to_datetime(series.index)
        data["returns"] = series.sort_index()
    else:
        data["returns"] = None
    return data
