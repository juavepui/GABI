"""Compatibility for frozen factor engines; modern jobs use explicit factor ports."""
import pandas as pd

from gabi.application.research.academic_factors import refresh_factors
from gabi.domain.research import academic_factors as _implementation
from gabi.infrastructure.providers import academic_factors as factor_source
from gabi.infrastructure.providers.academic_factors import FrenchFactorSource

from . import config

FF5_URL, MOM_URL = factor_source.FF5_URL, factor_source.MOM_URL
DEFAULT_FACTOR_COLS = list(_implementation.DEFAULT_FACTOR_COLS)
_parse_monthly_csv = _implementation._parse_monthly_csv
quarterly_period_return = _implementation.quarterly_period_return
_ols = _implementation._ols


def _download_zip_csv(url: str) -> str:
    return FrenchFactorSource().csv(url)


class _Source:
    def tables(self) -> tuple[str, str]:
        return _download_zip_csv(FF5_URL), _download_zip_csv(MOM_URL)


class _Cache:
    def __init__(self, directory):
        self.directory = directory
        self.path = directory / "ff_factors.csv"

    def load(self):
        return pd.read_csv(self.path, index_col=0, parse_dates=True) if self.path.exists() else None

    def save(self, frame: pd.DataFrame) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        frame.to_csv(self.path)


def fetch_ff_factors(force_refresh: bool = False) -> pd.DataFrame:
    return refresh_factors(_Cache(config.DATA_DIR), _Source(), force_refresh=force_refresh)


def regress_returns_on_factors(period_returns: pd.DataFrame, factors: pd.DataFrame,
                               factor_cols: list = None, *, hac_lags: int | None = None) -> dict:
    return _implementation.regress_returns_on_factors(period_returns, factors,
                                                     factor_cols or DEFAULT_FACTOR_COLS, hac_lags=hac_lags)
