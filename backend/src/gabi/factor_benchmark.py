"""Benchmarks trimestrales sin alfa: SPY ajustado por beta y FF5+Momentum.

Dos protocolos explícitos: atribución in-sample y estimación expansiva con
un trimestre de embargo. Las series sintéticas no representan ETFs replicables
ni atribuyen causalmente el residuo a selección de valores.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import academic_factors as af
from . import factor_stability as fs

MODELS = {"spy_beta": ["SPY-RF"], "ff6": af.DEFAULT_FACTOR_COLS}
MIN_TRAIN = 18
EMBARGO = 1
LIMITATIONS = [
    "In-sample utiliza betas de toda la muestra; es atribución retrospectiva, no una estrategia sin anticipación.",
    "Expanding ajusta solo trimestres anteriores y deja uno de embargo; no usa el retorno evaluado para estimar betas.",
    "Los factores son históricos revisados, sin vintages de publicación; el embargo no certifica disponibilidad point-in-time.",
    "Los modelos y la estrategia se eligieron tras explorar este histórico: expanding tampoco es validación prospectiva limpia.",
    "El benchmark excluye el intercepto: RF + beta*(SPY-RF) o RF + suma(beta_j*factor_j).",
    "La beta de SPY y la beta parcial Mkt-RF de FF5+Mom son estimandos diferentes; Mkt-RF no es SPY.",
    "Betas sin restricciones pueden implicar leverage o posiciones cortas. RF es financiación/caja idealizada, sin spreads.",
    "Factores long-short académicos no son productos directamente replicables: se omiten costes, impuestos y préstamo de títulos.",
    "El residual puede incluir exposición omitida, timing, ruido y sesgos; no se interpreta automáticamente como habilidad de selección.",
    "El alfa OLS, la diferencia de CAGR y el exceso de riqueza compuesta son magnitudes distintas.",
    "La alineación mensual aproxima fechas bursátiles; persisten las limitaciones de universo e identidad del backtest V1.",
]


def validate_inputs(inputs: pd.DataFrame) -> pd.DataFrame:
    frame = fs.validate_inputs(inputs)
    if "spy" not in inputs:
        raise ValueError("Se requiere la serie SPY de las mismas ventanas, no la beta histórica resumida.")
    # fs ordena las filas; aquí alineamos por fechas y no por su posición original.
    extra = inputs.copy()
    extra["fecha"] = pd.to_datetime(extra["fecha"])
    columns = ["spy"] + (["universo_ew"] if "universo_ew" in extra else [])
    frame = frame.merge(extra[["fecha", *columns]], on="fecha", how="left", validate="one_to_one")
    if not np.isfinite(frame[columns].to_numpy(dtype=float)).all() or (frame[columns] <= -1).any().any():
        raise ValueError("SPY/universo requieren retornos finitos y mayores que -100%, sin imputación.")
    frame["SPY-RF"] = frame["spy"] - frame["RF"]
    return frame


def aligned_inputs(periods: pd.DataFrame, factors: pd.DataFrame) -> pd.DataFrame:
    aligned = fs.aligned_quarters(periods, factors)
    extras = periods.copy()
    extras["fecha"] = pd.to_datetime(extras["fecha"])
    columns = ["fecha", "spy"] + (["universo_ew"] if "universo_ew" in extras else [])
    return validate_inputs(aligned.merge(extras[columns], on="fecha", validate="one_to_one"))


def _fit(frame: pd.DataFrame, columns: list[str]) -> dict:
    X = np.column_stack([np.ones(len(frame)), frame[columns].to_numpy()])
    fit = af._ols(frame["excess_return"].to_numpy(), X, ["alpha", *columns])
    fit["alpha_annualized"] = float((1 + fit["coef"]["alpha"]) ** 4 - 1)
    return fit


def _comparison(frame: pd.DataFrame, benchmarks: pd.DataFrame) -> dict:
    """Todas las curvas se reinician en 1 en la misma fecha; sin rellenar warm-up."""
    returns = pd.DataFrame({"strategy": frame["retorno"].to_numpy(), "spy": frame["spy"].to_numpy(),
                            "rf": frame["RF"].to_numpy()}, index=benchmarks.index)
    if "universo_ew" in frame:
        returns["universe_ew"] = frame["universo_ew"].to_numpy()
    for name in benchmarks:
        returns[name] = benchmarks[name]
    if not np.isfinite(returns.to_numpy()).all() or (returns <= -1).any().any():
        raise ValueError("Curva sintética no capitalizable: retorno no finito o <=-100%. No se recorta ni omite.")
    wealth = (1 + returns).cumprod()
    years = len(frame) / 4
    metrics = {name: {"total_return": float(wealth[name].iloc[-1] - 1),
                      "cagr": float(wealth[name].iloc[-1] ** (1 / years) - 1)} for name in returns}
    active = {}
    for name in benchmarks:
        diff = returns["strategy"] - returns[name]
        active[name] = {
            "mean_active_per_quarter": float(diff.mean()),
            "cagr_difference": metrics["strategy"]["cagr"] - metrics[name]["cagr"],
            "relative_wealth_return": float(wealth["strategy"].iloc[-1] / wealth[name].iloc[-1] - 1),
        }
    rows = []
    for i, (_, row) in enumerate(frame.iterrows()):
        rows.append({"fecha": row["fecha"].date().isoformat(), "hasta": row["hasta"].date().isoformat(),
                     "returns": returns.iloc[i].to_dict(), "wealth": wealth.iloc[i].to_dict(),
                     "active": {name: float(returns["strategy"].iloc[i] - returns[name].iloc[i]) for name in benchmarks}})
    return {"n_obs": len(frame), "start": rows[0]["fecha"], "end": rows[-1]["hasta"],
            "periods_per_year": 4, "metrics": metrics, "active": active, "periods": rows}


def analyze(inputs: pd.DataFrame) -> dict:
    frame = validate_inputs(inputs)
    if len(frame) < MIN_TRAIN:
        raise ValueError(f"Se requieren al menos {MIN_TRAIN} trimestres para el diagnóstico completo.")
    full_fits = {name: _fit(frame, columns) for name, columns in MODELS.items()}
    fitted = pd.DataFrame(index=frame.index)
    for name, columns in MODELS.items():
        beta = np.array([full_fits[name]["coef"][column] for column in columns])
        fitted[name] = frame["RF"] + frame[columns].to_numpy() @ beta
    full = _comparison(frame, fitted)
    full["regressions"] = full_fits
    predictions = []
    coefficients = []
    for i in range(MIN_TRAIN + EMBARGO, len(frame)):
        training = frame.iloc[:i - EMBARGO]
        # Comprobación de madurez sobre fechas reales, además del embargo por fila.
        if training["hasta"].max() >= frame["fecha"].iloc[i]:
            raise ValueError("El entrenamiento incluye retornos aún no observados en la fecha evaluada.")
        prediction: dict = {"position": i}
        for name, columns in MODELS.items():
            fit = _fit(training, columns)
            beta = np.array([fit["coef"][column] for column in columns])
            prediction[name] = float(frame["RF"].iloc[i] + frame.iloc[i][columns].to_numpy(dtype=float) @ beta)
            coefficients.append({"model": name, "evaluation_start": frame["fecha"].iloc[i].date().isoformat(),
                                 "train_start": training["fecha"].iloc[0].date().isoformat(),
                                 "train_end": training["hasta"].iloc[-1].date().isoformat(),
                                 "n_train": len(training), "coef": fit["coef"]})
        predictions.append(prediction)
    expanding: dict = {"status": "insufficient_history", "n_obs": 0, "coefficients": []}
    if predictions:
        predicted = pd.DataFrame(predictions).set_index("position")
        expanding = {"status": "ok", **_comparison(frame.loc[predicted.index], predicted),
                     "coefficients": coefficients}
    return {"schema_version": 1, "stage": "RESEARCH", "method": {
        "models": MODELS, "min_train": MIN_TRAIN, "embargo_quarters": EMBARGO,
        "intercept_in_benchmark": False, "coefficient_constraints": "none",
        "financing": "RF, same rate for cash and borrowing; no extra implementation costs",
    }, "in_sample": full, "expanding": expanding, "limitations": LIMITATIONS}


def curve_table(comparison: dict) -> pd.DataFrame:
    rows = [{"date": comparison["start"], **{name: 1. for name in comparison["metrics"]}}]
    rows.extend({"date": row["hasta"], **row["wealth"]} for row in comparison["periods"])
    return pd.DataFrame(rows).set_index("date")


def write_audit(input_path: Path, output_dir: Path) -> dict:
    audit = analyze(pd.read_csv(input_path))
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "inputs.csv").write_bytes(input_path.read_bytes())
    exports = ["inputs.csv"]
    for protocol in ("in_sample", "expanding"):
        if audit[protocol]["n_obs"]:
            name = f"{protocol}-curves.csv"
            curve_table(audit[protocol]).to_csv(output_dir / name)
            exports.append(name)
    audit["provenance"] = {
        "input_sha256": fs.content_hash(input_path),
        "source_code": {p.name: fs.content_hash(p) for p in (Path(__file__), Path(af.__file__), Path(fs.__file__))},
        "artifacts": {name: fs.content_hash(output_dir / name) for name in exports},
    }
    audit = fs._json_safe(audit)
    (output_dir / "audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                                          encoding="utf-8")
    return audit


def load_audit(output_dir: Path) -> dict:
    audit = json.loads((output_dir / "audit.json").read_text(encoding="utf-8"))
    expected = ["inputs.csv", "in_sample-curves.csv"]
    if audit["expanding"]["n_obs"]:
        expected.append("expanding-curves.csv")
    for name in expected:
        if fs.content_hash(output_dir / name) != audit["provenance"]["artifacts"][name]:
            raise ValueError(f"Ha cambiado el artefacto de benchmark: {name}")
    return audit


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, default=Path("docs/factor-benchmark/inputs.csv"))
    parser.add_argument("--output", type=Path, default=Path("docs/factor-benchmark"))
    args = parser.parse_args()
    audit = write_audit(args.inputs, args.output)
    print(f"In-sample: {audit['in_sample']['n_obs']}; expanding: {audit['expanding']['n_obs']}; {args.output}")


if __name__ == "__main__":
    main()
