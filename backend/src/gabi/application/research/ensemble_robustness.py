"""Coordinate the preregistered #53 robustness study over an explicit, return-free input port."""

from typing import Protocol

import numpy as np
import pandas as pd

from gabi.domain.research import ensemble_robustness as ens

SEALED_SPEC_SHA256 = "8609a0770a49d00c72bf5bb507d55551eba88b895543b305ca66715292555bca"


class EnsembleInputs(Protocol):
    def preregistration(self) -> dict: ...

    def scores(self, columns: list[str]) -> pd.DataFrame: ...

    def risk(self, date: str, columns: list[str]) -> pd.DataFrame: ...

    def fingerprints(self) -> dict: ...


def _window(date: str) -> str:
    year = int(date[:4])
    return "2011-15" if year <= 2015 else "2016-20" if year <= 2020 else "2021-25"


def analyze(inputs: EnsembleInputs) -> tuple[dict, dict[str, pd.DataFrame]]:
    record = inputs.preregistration()
    spec = record["spec"]
    if ens.fingerprint(spec) != record["sha256"] or record["sha256"] != SEALED_SPEC_SHA256:
        raise ValueError("La especificación sellada de #53 ha cambiado.")
    scores = inputs.scores(spec["inputs"]["scores"]["columns"])
    if scores.duplicated(["fecha", "symbol"]).any() or scores.entity_id.isna().any():
        raise ValueError("Símbolos duplicados o emisores sin identidad en una fecha.")
    # Two symbols of one issuer on a date are kept and counted as positions (CORRECCION.md).
    ens.check_published_blocks(scores, spec)  # before any other calculation

    calendar = sorted(scores.fecha.unique())
    if len(calendar) != 57 or calendar[0] != "2011-07-02" or calendar[-1] != "2025-07-02":
        raise ValueError("Calendario de #53 distinto del declarado.")
    minimum = spec["universe"]["minimum_size"]
    slots = spec["portfolios"]["slots"]
    p2 = spec["endpoints"]["P2_noise_persistence"]
    deltas = [p2["delta"], *p2["sensitivity_delta"]]
    generators = {delta: np.random.default_rng(p2["seed"]) for delta in deltas}

    rows, selection_rows, noise_rows, transitions = [], [], [], []
    previous: tuple[pd.DataFrame, dict] | None = None
    for date in calendar:
        eligible = scores.loc[scores.fecha == date]
        frame = ens.universe(eligible).set_index("symbol", drop=False)
        row = {"fecha": date, "n_eligible": len(eligible), "n_universe": len(frame),
               "evaluable": len(frame) >= minimum}
        if not row["evaluable"]:
            rows.append(row)
            previous = None
            continue
        risk = inputs.risk(date, spec["inputs"]["ex_ante_risk"]["columns"])
        missing = frame.index.difference(risk.index)
        if len(missing):
            raise ValueError(f"Empresas de U_t sin fila en el ranking congelado {date}: {list(missing)[:5]}")
        if not risk.loc[frame.index, "entity_id"].equals(frame.entity_id):
            raise ValueError(f"Identidad distinta entre scores y ranking congelado: {date}")
        metrics, selections = ens.date_metrics(frame, risk.loc[frame.index], spec)
        row.update(metrics)
        for name, chosen in selections.items():
            selection_rows += [{"fecha": date, "signal": name, "entity_id": entity, "positions": count}
                               for entity, count in sorted(chosen.items())]
        for delta in deltas:
            persistence = ens.noise_persistence(frame, spec, selections, generators[delta], delta)
            noise_rows.append({"fecha": date, "delta": delta, **persistence})
        if previous is not None:
            before_frame, before_selections = previous
            transitions.append({"fecha": date, "window": _window(date),
                                **{name: ens.turnover(before_selections[name], selections[name], slots)
                                   for name in ens.SIGNALS},
                                **{(key if key.startswith("excluded") else f"autocorr_{key}"): value
                                   for key, value in ens.autocorrelation(before_frame, frame, spec).items()}})
        previous = (frame, selections)
        rows.append(row)

    per_date = pd.DataFrame(rows)
    turnover = pd.DataFrame(transitions)
    noise = pd.DataFrame(noise_rows)
    selection = pd.DataFrame(selection_rows)
    primary_noise = noise.loc[noise.delta == p2["delta"]].reset_index(drop=True)
    complete = bool(per_date.evaluable.all())
    seed = spec["inference"]["seed"]
    p1 = ens.bootstrap_differences(turnover, spec, seed) if complete else None
    p2_intervals = ens.bootstrap_differences(primary_noise, spec, seed + 1) if complete else None
    evaluable = per_date.loc[per_date.evaluable]
    redundancy = {column.removeprefix("spearman_"): float(evaluable[column].mean())
                  for column in evaluable if column.startswith("spearman_")}
    dominance = float(evaluable.dominance.mean())
    result = {
        "issue": 53, "model": spec["model"], "spec_sha256": record["sha256"], "stage": spec["stage"],
        "demonstrated": False, "returns_read": False,
        "n_dates": len(calendar), "n_evaluable": int(per_date.evaluable.sum()),
        "universe_size": {"min": int(evaluable.n_universe.min()), "median": float(evaluable.n_universe.median()),
                          "max": int(evaluable.n_universe.max())},
        "coverage_of_eligible": float((evaluable.n_universe / evaluable.n_eligible).mean()),
        "P1_turnover_mean": {name: float(turnover[name].mean()) for name in ens.SIGNALS},
        "P1_turnover_by_window": {window: {name: float(group[name].mean()) for name in ens.SIGNALS}
                                  for window, group in turnover.groupby("window")},
        "P2_noise_persistence_mean": {str(delta): {name: float(group[name].mean()) for name in ens.SIGNALS}
                                      for delta, group in noise.groupby("delta")},
        "P1_intervals": p1, "P2_intervals": p2_intervals,
        "redundancy_spearman_mean": redundancy,
        "jaccard_mean": {column.removeprefix("jaccard_"): float(evaluable[column].mean())
                         for column in evaluable if column.startswith("jaccard_")},
        "dominance_mean": dominance,
        "score_autocorrelation_mean": {name: float(turnover[f"autocorr_{name}"].mean()) for name in ens.SIGNALS},
        "duplicated_entity_dates": int(scores.duplicated(["fecha", "entity_id"], keep=False).groupby(
            scores.fecha).any().sum()),
        "autocorrelation_excluded_entities_total": int(turnover.excluded_duplicated_entities.sum()),
        "concentration_mean": {name: {"divisions": float(evaluable[f"{name}_divisions"].mean()),
                                      "division_hhi": float(evaluable[f"{name}_division_hhi"].mean()),
                                      "cash_slots": float(evaluable[f"{name}_cash_slots"].mean())}
                               for name in ens.SIGNALS},
        "ex_ante_risk_mean": {name: {**{column: float(evaluable[f"{name}_{column}_mean"].mean())
                                        for column in ens.RISK_MEANS},
                                     "market_cap_median": float(evaluable[f"{name}_market_cap_median"].mean())}
                              for name in (*ens.SIGNALS, "universe")},
        "decision": ens.decide(redundancy, dominance, p1, p2_intervals),
        "inputs": inputs.fingerprints(),
    }
    tables = {"por_fecha.csv": per_date, "rotacion.csv": turnover, "ruido.csv": noise, "selecciones.csv": selection}
    return result, tables
