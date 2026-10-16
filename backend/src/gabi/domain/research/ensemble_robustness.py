"""Return-free robustness of the preregistered V+Q+E ensemble (#53).

Every rule comes from ``docs/ensemble-robustness/preregistro.json``. The functions only see
block/metric percentiles, SIC divisions and ex ante risk features; no return enters here.
"""

import hashlib
import json
import math
from collections import Counter
from itertools import combinations

import numpy as np
import pandas as pd

BLOCKS = ("value", "quality", "expectations")
SIGNALS = ("ENS", *BLOCKS)
RISK_MEANS = ("volatility", "max_drawdown", "beta_calc")


def fingerprint(value: object) -> str:
    data = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def json_ready(value):
    """Plain JSON types; a non-finite statistic is published as an explicit absence (null)."""
    if isinstance(value, dict):
        return {str(key): json_ready(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [json_ready(item) for item in value]
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def metric_columns(spec: dict) -> list[str]:
    metrics = spec["components"]["metrics"]
    return [column for block in BLOCKS for column in metrics[block]]


def blocks(frame: pd.DataFrame, spec: dict, noise: np.ndarray | None = None) -> pd.DataFrame:
    """Block = mean of available metric percentiles with the declared minimum; optional additive noise."""
    metrics = frame[metric_columns(spec)].to_numpy(dtype=float, copy=True)
    if noise is not None:
        metrics = metrics + noise  # NaN stays NaN: availability and U_t do not change
    table = pd.DataFrame(metrics, index=frame.index, columns=metric_columns(spec))
    result = pd.DataFrame(index=frame.index)
    for block in BLOCKS:
        columns = spec["components"]["metrics"][block]
        available = table[columns].notna().sum(axis=1)
        minimum = spec["components"]["block_minimum_available"][block]
        result[block] = table[columns].mean(axis=1).where(available >= minimum)
    return result


def check_published_blocks(frame: pd.DataFrame, spec: dict) -> None:
    """The recomputed blocks must reproduce the published #60 columns before any other step."""
    recomputed = blocks(frame, spec)
    for block in BLOCKS:
        published = frame[block].astype(float)
        if not recomputed[block].isna().equals(published.isna()):
            raise ValueError(f"Disponibilidad del bloque distinta de la publicada: {block}")
        both = published.notna()
        if both.any() and float((recomputed.loc[both, block] - published[both]).abs().max()) > 1e-12:
            raise ValueError(f"Bloque recalculado distinto del publicado: {block}")


def signals(block_table: pd.DataFrame, spec: dict) -> pd.DataFrame:
    weights = spec["aggregation"]["weights"]
    result = block_table[list(BLOCKS)].copy()
    result.insert(0, "ENS", sum(block_table[block] * weights[block] for block in BLOCKS))
    return result


def universe(frame: pd.DataFrame) -> pd.DataFrame:
    """U_t: all three published blocks present, ordered by symbol."""
    return frame.loc[frame[list(BLOCKS)].notna().all(axis=1)].sort_values("symbol")


def select(score: pd.Series, frame: pd.DataFrame, spec: dict) -> tuple[list[str], int]:
    """Top-N symbols with a per-division cap; ties by symbol; empty slots are cash."""
    rules = spec["portfolios"]
    ordered = pd.DataFrame({"score": score, "symbol": frame["symbol"], "division": frame["division"],
                            "entity_id": frame["entity_id"]}).rename_axis(None).sort_values(["score", "symbol"], ascending=[False, True])
    chosen: list[str] = []
    counts: dict[str, int] = {}
    for row in ordered.itertuples(index=False):
        if len(chosen) == rules["slots"]:
            break
        if counts.get(row.division, 0) >= rules["maximum_per_division"]:
            continue
        counts[row.division] = counts.get(row.division, 0) + 1
        chosen.append(row.symbol)
    return chosen, rules["slots"] - len(chosen)


def positions(frame: pd.DataFrame, symbols: list[str]) -> Counter:
    """Positions by entity_id as a multiset (CORRECCION.md): two share classes of one issuer fill two
    slots, and a ticker change of the same issuer is not turnover. ``frame`` is indexed by symbol."""
    return Counter(frame.loc[symbols, "entity_id"])


def _share(a: Counter, b: Counter, slots: int) -> float:
    return sum((a & b).values()) / slots


def _jaccard(a: Counter, b: Counter) -> float:
    union = sum((a | b).values())
    return sum((a & b).values()) / union if union else math.nan


def _spearman(a: pd.Series, b: pd.Series) -> float:
    return float(a.rank().corr(b.rank()))


def noise_persistence(frame: pd.DataFrame, spec: dict, base: dict[str, Counter],
                      rng: np.random.Generator, delta: float) -> dict[str, float]:
    """Mean share of each base Top-20 that survives uniform percentile noise; same draws for all signals."""
    rules = spec["endpoints"]["P2_noise_persistence"]
    slots = spec["portfolios"]["slots"]
    if not (frame["symbol"].is_monotonic_increasing and frame["symbol"].is_unique):
        raise ValueError("U_t debe estar ordenado por symbol sin duplicados.")
    metrics = frame[metric_columns(spec)].to_numpy(dtype=float)
    totals = dict.fromkeys(SIGNALS, 0.0)
    for _ in range(rules["replicates"]):
        draws = rng.uniform(-delta, delta, size=metrics.shape)
        perturbed = _fast_signals(metrics + draws, spec)
        for position, name in enumerate(SIGNALS):
            totals[name] += _share(_fast_select(perturbed[position], frame, spec), base[name], slots)
    return {name: totals[name] / rules["replicates"] for name in SIGNALS}


def _fast_signals(metrics: np.ndarray, spec: dict) -> list[np.ndarray]:
    """Array twin of ``signals(blocks(...))``: same skip-NaN mean, minimums and summation order."""
    columns = metric_columns(spec)
    result = []
    for block in BLOCKS:
        positions = [columns.index(name) for name in spec["components"]["metrics"][block]]
        part = metrics[:, positions]
        available = (~np.isnan(part)).sum(axis=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            mean = np.nansum(part, axis=1) / available
        minimum = spec["components"]["block_minimum_available"][block]
        result.append(np.where(available >= minimum, mean, np.nan))
    weights = spec["aggregation"]["weights"]
    ensemble = result[0] * weights["value"] + result[1] * weights["quality"] + result[2] * weights["expectations"]
    return [ensemble, *result]


def _fast_select(score: np.ndarray, frame: pd.DataFrame, spec: dict) -> Counter:
    """Array twin of ``select`` for frames already ordered by symbol (``universe``)."""
    rules = spec["portfolios"]
    order = np.lexsort((np.arange(len(score)), -score))
    divisions = frame["division"].to_numpy()
    entities = frame["entity_id"].to_numpy()
    chosen: list[str] = []
    counts: dict[str, int] = {}
    for index in order:
        if len(chosen) == rules["slots"]:
            break
        if counts.get(divisions[index], 0) >= rules["maximum_per_division"]:
            continue
        counts[divisions[index]] = counts.get(divisions[index], 0) + 1
        chosen.append(entities[index])
    return Counter(chosen)


def date_metrics(frame: pd.DataFrame, risk: pd.DataFrame, spec: dict) -> tuple[dict, dict[str, Counter]]:
    """Per-date descriptive metrics on U_t, plus the four base selections."""
    scores = signals(frame, spec)
    slots = spec["portfolios"]["slots"]
    selections: dict[str, Counter] = {}
    row: dict = {"n_universe": len(frame)}
    for name in SIGNALS:
        chosen, cash = select(scores[name], frame, spec)
        selections[name] = positions(frame, chosen)
        members = frame.loc[chosen]
        weights = members.division.value_counts() / slots
        row[f"{name}_cash_slots"] = cash
        row[f"{name}_divisions"] = int(members.division.nunique())
        row[f"{name}_division_hhi"] = float((weights ** 2).sum())
        held = risk.loc[members.index]
        for column in RISK_MEANS:
            row[f"{name}_{column}_mean"] = float(held[column].mean()) if held[column].notna().any() else math.nan
            row[f"{name}_{column}_missing"] = int(held[column].isna().sum())
        row[f"{name}_market_cap_median"] = float(held.market_cap.median()) if held.market_cap.notna().any() else math.nan
        row[f"{name}_market_cap_missing"] = int(held.market_cap.isna().sum())
    for column in RISK_MEANS:
        row[f"universe_{column}_mean"] = float(risk[column].mean())
        row[f"universe_{column}_missing"] = int(risk[column].isna().sum())
    row["universe_market_cap_median"] = float(risk.market_cap.median())
    row["universe_market_cap_missing"] = int(risk.market_cap.isna().sum())
    for a, b in combinations(BLOCKS, 2):
        row[f"spearman_{a}_{b}"] = _spearman(frame[a], frame[b])
    for a, b in combinations(SIGNALS, 2):
        row[f"jaccard_{a}_{b}"] = _jaccard(selections[a], selections[b])
    row["dominance"] = max(_share(selections["ENS"], selections[c], slots) for c in BLOCKS)
    return row, selections


def turnover(previous: Counter, current: Counter, slots: int) -> float:
    return 1 - sum((previous & current).values()) / slots


def autocorrelation(previous: pd.DataFrame, current: pd.DataFrame, spec: dict) -> dict[str, float]:
    """Spearman of each signal between consecutive dates for entities in U at both.

    Entities with two rows on either date (share classes) are excluded and counted.
    """
    duplicated = set(previous.entity_id[previous.entity_id.duplicated()]) | set(
        current.entity_id[current.entity_id.duplicated()])
    before = signals(previous, spec).set_axis(previous.entity_id)
    after = signals(current, spec).set_axis(current.entity_id)
    common = before.index.intersection(after.index).difference(pd.Index(sorted(duplicated)))
    result: dict[str, float] = {
        name: _spearman(before.loc[common, name], after.loc[common, name]) if len(common) >= 3 else math.nan
        for name in SIGNALS}
    result["excluded_duplicated_entities"] = len(duplicated)
    return result


def circular_indices(n: int, block: int, replicas: int, rng: np.random.Generator) -> np.ndarray:
    starts = rng.integers(0, n, size=(replicas, math.ceil(n / block)))
    offsets = np.arange(block)
    return ((starts[:, :, None] + offsets) % n).reshape(replicas, -1)[:, :n]


def bootstrap_differences(table: pd.DataFrame, spec: dict, seed: int) -> dict | None:
    """Percentile intervals of mean(ENS - c) for the three components, joint resampling; None with any gap."""
    rules = spec["inference"]
    columns = ["ENS", *BLOCKS]
    if table[columns].isna().to_numpy().any():
        return None
    values = table[columns].to_numpy(dtype=float)
    indices = circular_indices(len(values), rules["block_length"], rules["replicas"], np.random.default_rng(seed))
    alpha = 0.05 / rules["comparisons"]
    result = {}
    for position, component in enumerate(BLOCKS, start=1):
        difference = values[:, 0] - values[:, position]
        means = difference[indices].mean(axis=1)
        low, high = np.quantile(means, [alpha / 2, 1 - alpha / 2])
        result[component] = {"observed": float(difference.mean()), "low": float(low), "high": float(high)}
    return result


def decide(redundancy: dict[str, float], dominance: float, p1: dict | None, p2: dict | None) -> dict:
    redundant = any(value >= 0.80 for value in redundancy.values())
    dominated = dominance >= 0.75
    criteria: dict[str, bool | None] = {"no_redundancy": not redundant, "no_dominance": not dominated}
    for component in BLOCKS:
        criteria[f"P1_vs_{component}"] = None if p1 is None else p1[component]["high"] < 0
        criteria[f"P2_vs_{component}"] = None if p2 is None else p2[component]["low"] > 0
    interval_criteria = [value for key, value in criteria.items() if key.startswith("P")]
    if redundant:
        label = "redundante"
    elif dominated:
        label = "equivalente_a_un_componente"
    elif any(value is None for value in interval_criteria):
        label = "no_estimable"
    elif all(interval_criteria):
        label = "mas_robusto"
    elif any(interval_criteria):
        label = "parcial"
    else:
        label = "sin_mejora"
    return {"label": label, "criteria": criteria, "prospective_v1_allowed": not redundant}
