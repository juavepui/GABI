"""Rutas y parámetros por defecto de GABI."""
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "gabi.db"
SP500_CACHE = DATA_DIR / "sp500_constituents.csv"
WEIGHTS_PATH = DATA_DIR / "weights.json"

BENCHMARK_SYMBOL = "SPY"

# Cuánto tiempo se consideran "frescos" los fundamentales antes de re-descargarlos.
CACHE_MAX_AGE_HOURS = 24

# Parámetros técnicos.
SMA_SHORT = 50
SMA_LONG = 200
RSI_PERIOD = 14
MOMENTUM_SHORT_DAYS = 126  # ~6 meses de sesiones
MOMENTUM_LONG_DAYS = 252  # ~12 meses de sesiones

# Pesos por defecto del score compuesto.
DEFAULT_WEIGHTS = {"value": 0.35, "quality": 0.35, "momentum": 0.30}

# Subconjunto de campos de yfinance Ticker.info que nos interesan (evita
# guardar el dict completo, que trae mucho ruido y cambia entre versiones).
INFO_KEYS = [
    "shortName", "sector", "industry", "marketCap",
    "trailingPE", "forwardPE", "pegRatio", "priceToBook",
    "priceToSalesTrailing12Months", "enterpriseToEbitda",
    "returnOnEquity", "returnOnAssets", "operatingMargins",
    "grossMargins", "profitMargins", "debtToEquity", "currentRatio",
    "revenueGrowth", "earningsGrowth", "freeCashflow", "operatingCashflow",
    "trailingEps", "forwardEps", "beta",
    "fiftyTwoWeekHigh", "fiftyTwoWeekLow", "currentPrice", "regularMarketPrice",
]


def load_weights():
    if WEIGHTS_PATH.exists():
        try:
            return json.loads(WEIGHTS_PATH.read_text())
        except Exception:
            pass
    return dict(DEFAULT_WEIGHTS)


def save_weights(weights):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    WEIGHTS_PATH.write_text(json.dumps(weights))
