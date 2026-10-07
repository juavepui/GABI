"""Compatibility for frozen factor engines; modern jobs use explicit factor ports."""
import io
import zipfile

import pandas as pd
import requests

from gabi.application.research.academic_factors import refresh_factors
from gabi.domain.research import academic_factors as _implementation

from . import config

FF5_URL = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_5_Factors_2x3_CSV.zip"
MOM_URL = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Momentum_Factor_CSV.zip"
_HEADERS = {"User-Agent": "GABI (herramienta personal de análisis, uso no comercial)"}
DEFAULT_FACTOR_COLS = list(_implementation.DEFAULT_FACTOR_COLS)
_parse_monthly_csv = _implementation._parse_monthly_csv
quarterly_period_return = _implementation.quarterly_period_return
_ols = _implementation._ols


def _download_zip_csv(url: str) -> str:
    resp = requests.get(url, timeout=30, headers=_HEADERS)
    resp.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(resp.content))
    with z.open(z.namelist()[0]) as f:
        return f.read().decode("utf-8", errors="replace")


class _Cache:
    def __init__(self, directory):
        self.directory = directory
        self.path = directory / "ff_factors.csv"

    def load(self):
        return pd.read_csv(self.path, index_col=0, parse_dates=True) if self.path.exists() else None

    def save(self, frame: pd.DataFrame) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        frame.to_csv(self.path)


class _Source:
    def tables(self) -> tuple[str, str]:
        return _download_zip_csv(FF5_URL), _download_zip_csv(MOM_URL)


def fetch_ff_factors(force_refresh: bool = False) -> pd.DataFrame:
    return refresh_factors(_Cache(config.DATA_DIR), _Source(), force_refresh=force_refresh)


def regress_returns_on_factors(period_returns: pd.DataFrame, factors: pd.DataFrame,
                               factor_cols: list = None, *, hac_lags: int | None = None) -> dict:
    return _implementation.regress_returns_on_factors(period_returns, factors,
                                                     factor_cols or DEFAULT_FACTOR_COLS, hac_lags=hac_lags)
