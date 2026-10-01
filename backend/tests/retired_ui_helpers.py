"""Reference copy of `ui_helpers.build_color_basis`, retired with Streamlit (#68).

Kept verbatim so the React historical table keeps being compared with the colours the old page used.
"""

import pandas as pd

SCORE_COLUMNS = {"value_score", "quality_score", "momentum_score", "risk_score", "composite_score", "confidence"}


def build_color_basis(df: pd.DataFrame, columns) -> pd.DataFrame:
    """DataFrame con la misma forma que df[columns] pero con el percentil
    0-100 (100=mejor) que debe usarse como base del color de cada celda.

    Para las columnas de score usa el propio valor (ya está en 0-100); para
    el resto usa la columna '<col>_pct' que calcula scoring.build_scores.
    Si no hay percentil disponible, la celda queda sin color (NaN)."""
    basis = pd.DataFrame(index=df.index)
    for col in columns:
        if col in SCORE_COLUMNS and col in df.columns:
            basis[col] = df[col]
        elif col + "_pct" in df.columns:
            basis[col] = df[col + "_pct"]
        else:
            basis[col] = float("nan")
    return basis
