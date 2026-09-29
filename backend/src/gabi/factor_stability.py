"""Auditoría retrospectiva de estabilidad FF5+Mom sobre retornos trimestrales.

No clasifica regímenes en tiempo real ni selecciona ventanas por significancia.
Los episodios cortos se describen con las betas de la muestra completa; las
regresiones locales requieren al menos dos observaciones por coeficiente.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import academic_factors as af

EVENTS = (
    ("selloff_2018", "2018: selloff (año completo)", "2018-01", "2019-01"),
    ("covid_2020", "2020: COVID y recuperación", "2020-01", "2021-01"),
    ("rates_2022", "2022: subida de tipos", "2022-01", "2023-01"),
    ("rally_2023_2024", "2023–2024: rally estrecho", "2023-01", "2025-01"),
)
NAMES = ["alpha", *af.DEFAULT_FACTOR_COLS]
MIN_OBS = 2 * len(NAMES)
WINDOWS = (16, 20, 24)
LIMITATIONS = [
    "RESEARCH retrospectivo: episodios elegidos con conocimiento histórico, no señal operable ni validación prospectiva.",
    "FF5+Mom estima siete coeficientes. El mínimo de 14 trimestres es una regla prudencial, no garantía de potencia.",
    "HAC e intervalos ±1.96 SE son aproximaciones asintóticas puntuales; no corrigen múltiples ventanas ni selección.",
    "Las ventanas móviles se solapan: no son replicaciones independientes ni una prueba formal de cambio estructural.",
    "La atribución usa betas de toda la muestra y es in-sample; su suma aritmética no es rentabilidad compuesta ni alfa local.",
    "Excluir episodios cambia la composición de la muestra. Se reportan coeficientes OLS sin inferencia HAC sobre huecos.",
    "Factores mensuales compuestos aproximan fechas bursátiles. Persisten sesgos del universo muestreado e identidad V1.",
    "El turnover histórico agregado del 63% no demuestra cambios de beta ni causalidad; aquí no se estima turnover por régimen.",
    "No se han recuperado las permutaciones ni los pesos completos de perturbaciones históricas: su estabilidad queda pendiente.",
]


def aligned_quarters(periods: pd.DataFrame, factors: pd.DataFrame) -> pd.DataFrame:
    """Alineación mensual estricta para esta auditoría, sin imputar RF ni meses.

    Cada fila representa un retorno real de tres meses. No se crean retornos
    mensuales dividiendo o interpolando observaciones trimestrales.
    """
    factors = factors.copy()
    factors.index = pd.DatetimeIndex(factors.index).to_period("M")
    if factors.index.has_duplicates:
        raise ValueError("Meses duplicados en factores.")
    rows = []
    for _, row in periods.iterrows():
        start, end = pd.Period(row["fecha"], "M"), pd.Period(row["hasta"], "M")
        if end.ordinal - start.ordinal != 3:
            raise ValueError("La auditoría temporal requiere retornos trimestrales reales.")
        months = pd.period_range(start, periods=3, freq="M")
        values = factors.reindex(months)[[*af.DEFAULT_FACTOR_COLS, "RF"]]
        if not np.isfinite(values.to_numpy(dtype=float)).all():
            raise ValueError(f"Faltan meses de factores/RF o valores finitos en {start}.")
        composed = (1 + values).prod() - 1
        rows.append({"fecha": row["fecha"], "hasta": row["hasta"], "retorno": row["retorno"],
                     **composed.to_dict(), "excess_return": row["retorno"] - composed["RF"]})
    return validate_inputs(pd.DataFrame(rows))


def validate_inputs(inputs: pd.DataFrame) -> pd.DataFrame:
    """Rechaza huecos, solapamientos mensuales, imputaciones y excesos incoherentes."""
    required = ["fecha", "hasta", "retorno", "RF", "excess_return", *af.DEFAULT_FACTOR_COLS]
    if not set(required).issubset(inputs.columns) or inputs.empty:
        raise ValueError("Faltan inputs de la regresión trimestral.")
    frame = inputs[required].copy()
    for column in ("fecha", "hasta"):
        frame[column] = pd.to_datetime(frame[column], errors="raise")
        if frame[column].isna().any():
            raise ValueError("Fechas ausentes.")
    frame = frame.sort_values("fecha").reset_index(drop=True)
    starts = pd.PeriodIndex(frame["fecha"], freq="M").asi8
    ends = pd.PeriodIndex(frame["hasta"], freq="M").asi8
    if not np.all(ends - starts == 3) or not np.all(starts[1:] == ends[:-1]):
        raise ValueError("Se requieren trimestres consecutivos sin huecos ni solapamientos mensuales.")
    if not np.isfinite(frame[required[2:]].to_numpy(dtype=float)).all():
        raise ValueError("Inputs no finitos.")
    if (frame[["retorno", "RF"]] <= -1).any().any():
        raise ValueError("Retorno/RF debe ser mayor que -100%.")
    if not np.allclose(frame["excess_return"], frame["retorno"] - frame["RF"], rtol=1e-10, atol=1e-12):
        raise ValueError("Exceso de retorno incoherente con retorno menos RF.")
    return frame


def _design(frame: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    return frame["excess_return"].to_numpy(), np.column_stack([
        np.ones(len(frame)), frame[af.DEFAULT_FACTOR_COLS].to_numpy(),
    ])


def _fit(frame: pd.DataFrame, *, inference: bool = True) -> dict:
    n = len(frame)
    result: dict = {"n_obs": n, "dof": n - len(NAMES), "status": "insufficient_data"}
    if n:
        result.update(start=frame["fecha"].iloc[0].date().isoformat(),
                      end=frame["hasta"].iloc[-1].date().isoformat())
    if n < MIN_OBS:
        return result
    y, X = _design(frame)
    beta, _, rank, _ = np.linalg.lstsq(X, y, rcond=None)
    if rank < len(NAMES):
        return {**result, "status": "rank_deficient"}
    result.update(status="ok", condition_number=float(np.linalg.cond(X)),
                  coef=dict(zip(NAMES, beta.tolist())), alpha_anualizado=float((1 + beta[0]) ** 4 - 1))
    if inference:
        result.update(af._ols(y, X, NAMES))
        result["ci95_pointwise"] = {
            name: [result["coef"][name] - 1.96 * result["se"][name],
                   result["coef"][name] + 1.96 * result["se"][name]] for name in NAMES
        }
    else:
        result["inference"] = "none: gaps after exclusion; coefficients only"
    return result


def analyze(inputs: pd.DataFrame) -> dict:
    """Muestra completa, mitades cronológicas, rolling y atribución por episodios.

    Los episodios usan límites mensuales [inicio, fin); solo se asignan
    trimestres íntegramente contenidos. El resto conserva todas las filas
    no asignadas y permite conciliar la atribución exactamente.
    """
    frame = validate_inputs(inputs)
    full = _fit(frame)
    if full["status"] != "ok":
        raise ValueError(f"Muestra completa no estimable: {full['status']} (mínimo {MIN_OBS}).")
    n = len(frame)
    y, X = _design(frame)
    beta = np.array([full["coef"][name] for name in NAMES])
    adjusted = y - X[:, 1:] @ beta[1:]
    residual = adjusted - beta[0]
    starts, ends = pd.PeriodIndex(frame["fecha"], freq="M"), pd.PeriodIndex(frame["hasta"], freq="M")
    assigned = np.zeros(n, dtype=bool)
    masks: list[tuple[str, str, str | None, str | None, np.ndarray]] = []
    for key, label, start, end in EVENTS:
        mask = np.asarray((starts >= pd.Period(start, "M")) & (ends <= pd.Period(end, "M")))
        assigned |= mask
        masks.append((key, label, start, end, mask))
    masks.append(("other", "Resto de trimestres", None, None, ~assigned))
    events = []
    for key, label, event_start, event_end, mask in masks:
        subset = frame.loc[mask]
        count = int(mask.sum())
        attribution = {
            "excess_sum": float(y[mask].sum()),
            "factor_contributions": {name: float((X[mask, i] * beta[i]).sum())
                                     for i, name in enumerate(NAMES[1:], start=1)},
            "adjusted_sum": float(adjusted[mask].sum()),
            "residual_sum": float(residual[mask].sum()),
            "contribution_to_full_quarterly_alpha": float(adjusted[mask].sum() / n),
        }
        events.append({
            "id": key, "label": label, "start_month": event_start, "end_month_exclusive": event_end,
            "n_obs": count, "period_starts": subset["fecha"].dt.strftime("%Y-%m-%d").tolist(),
            "compounded_return": float((1 + subset["retorno"]).prod() - 1) if count else None,
            "attribution": attribution,
            # El resto tiene huecos y no constituye un único régimen continuo.
            "local_regression": _fit(subset) if key != "other" else {"status": "not_contiguous"},
            "without_episode": _fit(frame.loc[~mask], inference=False) if count and key != "other" else None,
        })
    midpoint = n // 2
    halves = [{"id": key, **_fit(part)} for key, part in (
        ("first_half", frame.iloc[:midpoint]), ("second_half", frame.iloc[midpoint:]),
    )]
    rolling = []
    for window in WINDOWS:
        for stop in range(window, n + 1):
            rolling.append({"window": window, **_fit(frame.iloc[stop - window:stop])})
    attribution_rows = []
    for i, row in frame.iterrows():
        attribution_rows.append({
            "fecha": row["fecha"].date().isoformat(), "hasta": row["hasta"].date().isoformat(),
            "event": next(key for key, _, _, _, mask in masks if mask[i]),
            "excess_return": float(y[i]), "factor_adjusted_return": float(adjusted[i]),
            "residual": float(residual[i]),
            **{name: float(X[i, j] * beta[j]) for j, name in enumerate(NAMES[1:], start=1)},
        })
    calendar_years = []
    for year in sorted(frame["fecha"].dt.year.unique()):
        # No divide retornos que crucen el año: conserva la convención de inicio.
        mask = (frame["fecha"].dt.year == year).to_numpy()
        calendar_years.append({
            "year_of_start": int(year), "n_obs": int(mask.sum()),
            "compounded_return": float((1 + frame.loc[mask, "retorno"]).prod() - 1),
            "adjusted_sum": float(adjusted[mask].sum()),
            "contribution_to_full_quarterly_alpha": float(adjusted[mask].sum() / n),
        })
    return {"schema_version": 1, "stage": "RESEARCH", "n_obs": n,
            "method": {"factors": af.DEFAULT_FACTOR_COLS, "min_obs": MIN_OBS, "windows": list(WINDOWS),
                       "periods_per_year": 4, "hac_lags": "automatic separately for each contiguous window",
                       "event_boundaries": "monthly [start, end); only fully contained quarters"},
            "full": full, "halves": halves, "rolling": rolling, "events": events,
            "attribution_by_quarter": attribution_rows, "calendar_years": calendar_years,
            "limitations": LIMITATIONS}


def coefficient_table(audit: dict) -> pd.DataFrame:
    """Formato largo para gráficos y descarga; alfa en unidades trimestrales."""
    rows = []
    fits = [("full", audit["full"]), *((p["id"], p) for p in audit["halves"]),
            *((f"rolling_{p['window']}", p) for p in audit["rolling"])]
    for group, fit in fits:
        if fit["status"] != "ok":
            continue
        for name in NAMES:
            rows.append({"group": group, "start": fit["start"], "end": fit["end"], "n_obs": fit["n_obs"],
                         "dof": fit["dof"], "hac_lags": fit["hac_lags"], "coefficient": name,
                         "estimate": fit["coef"][name], "se_hac": fit["se"][name],
                         "t_hac": fit["t_stat"][name],
                         "ci_low": fit["ci95_pointwise"][name][0], "ci_high": fit["ci95_pointwise"][name][1]})
    return pd.DataFrame(rows)


def content_hash(path: Path) -> str:
    """Huella portable entre checkouts LF/CRLF."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _json_safe(value):
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def write_audit(input_path: Path, output_dir: Path) -> dict:
    audit = analyze(pd.read_csv(input_path))
    output_dir.mkdir(parents=True, exist_ok=True)
    # Copia autocontenida de los inputs, sin acceso a red ni a datos ciegos.
    (output_dir / "inputs.csv").write_bytes(input_path.read_bytes())
    coefficient_table(audit).to_csv(output_dir / "coefficients.csv", index=False)
    pd.DataFrame(audit["attribution_by_quarter"]).to_csv(output_dir / "attribution.csv", index=False)
    audit["provenance"] = {
        "source_input": input_path.name, "input_sha256": content_hash(input_path),
        "source_code": {p.name: content_hash(p) for p in (Path(__file__), Path(af.__file__))},
        "artifacts": {name: content_hash(output_dir / name)
                      for name in ("inputs.csv", "coefficients.csv", "attribution.csv")},
    }
    audit = _json_safe(audit)
    (output_dir / "audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                                          encoding="utf-8")
    return audit


def load_audit(output_dir: Path) -> dict:
    audit = json.loads((output_dir / "audit.json").read_text(encoding="utf-8"))
    for name in ("inputs.csv", "coefficients.csv", "attribution.csv"):
        if content_hash(output_dir / name) != audit["provenance"]["artifacts"][name]:
            raise ValueError(f"Ha cambiado el artefacto de estabilidad: {name}.")
    return audit


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, default=Path("docs/academic-factors-hac-inputs.csv"))
    parser.add_argument("--output", type=Path, default=Path("docs/factor-stability"))
    args = parser.parse_args()
    audit = write_audit(args.inputs, args.output)
    print(f"{audit['n_obs']} quarters, {len(audit['rolling'])} rolling fits; {args.output}")


if __name__ == "__main__":
    main()
