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

# SEC EDGAR exige un User-Agent identificable (no valida el email, solo pide
# que exista). Por defecto no usamos tu email real para no filtrarlo a un
# servicio de terceros en una cabecera HTTP; si quieres, cámbialo aquí por
# el tuyo (recomendado por la propia SEC para que puedan contactarte si hay
# uso excesivo, pero no es obligatorio que sea real).
SEC_USER_AGENT = "GABI-personal-investing-tool contact@example.com"

# Los informes anuales/trimestrales de SEC EDGAR cambian mucho menos a menudo
# que precios o el .info de yfinance, así que se cachean más tiempo.
EDGAR_CACHE_MAX_AGE_HOURS = 24 * 7

FRED_KEY_PATH = DATA_DIR / "fred_api_key.txt"

# Tipo libre de riesgo usado en Sharpe/Sortino/Alpha cuando no hay una API key
# de FRED configurada (si la hay, screener.py usa el Treasury 10 años en vivo).
RISK_FREE_RATE = 0.04

# Parámetros técnicos.
SMA_SHORT = 50
SMA_LONG = 200
RSI_PERIOD = 14
MOMENTUM_SHORT_DAYS = 126  # ~6 meses de sesiones
MOMENTUM_LONG_DAYS = 252  # ~12 meses de sesiones

# Pesos por defecto del score compuesto.
DEFAULT_WEIGHTS = {"value": 0.30, "quality": 0.35, "momentum": 0.25, "risk": 0.10}

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
    "trailingAnnualDividendYield", "averageDailyVolume3Month",
    # Calendario de eventos corporativos (gabi.events_calendar) -- Yahoo ya
    # las incluye en el mismo fetch de fundamentales, sin llamada aparte.
    "earningsTimestampStart", "earningsTimestampEnd", "isEarningsDateEstimate",
    "exDividendDate", "dividendDate",
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


def load_fred_key():
    if FRED_KEY_PATH.exists():
        key = FRED_KEY_PATH.read_text().strip()
        return key or None
    return None


def save_fred_key(key: str):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    FRED_KEY_PATH.write_text(key.strip())
