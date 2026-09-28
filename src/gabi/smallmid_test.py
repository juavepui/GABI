"""Prueba preregistrada de GABI fuera del S&P 500, con cotas para los datos que faltan (issue #44).

GABI se diseñó con el S&P 500; las empresas medianas y pequeñas de EE. UU. no
se usaron para diseñarlo. Aquí se aplica **sin cambios** (Composite 30/35/25/10,
mismas métricas, mismo filtro de cobertura) a un universo construido solo con
datos SEC, y se mide si ordena a esas empresas por su rentabilidad del
trimestre siguiente.

Los precios gratuitos no cubren a la mayoría de las empresas que desaparecen
(#44, estudio de viabilidad). Por eso la conclusión se juzga con **cotas
adversas**: a las empresas elegibles sin retorno siguiente se les asigna el
peor caso para la hipótesis. Este módulo contiene la especificación y la
construcción del universo; el resto de la tubería se añade por etapas sin
cambiar la especificación.
"""

import argparse
import functools
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from . import config, research_lab, scoring
from . import factor_stability as fs
from . import smallmid_feasibility as feas

OUTPUT = config.BASE_DIR / "docs" / "smallmid-test"
WORK = config.DATA_DIR / "smallmid_test"
FIRST, LAST = "2011-07-02", "2025-07-02"  # los mismos 57 rebalanceos que el #35 y el #40

SIC_SECTORS = [  # división SIC → sector amplio (aproximación documentada al GICS)
    ((100, 999), "Materials"), ((1000, 1499), "Materials"), ((1311, 1389), "Energy"),
    ((1500, 1799), "Industrials"), ((2000, 2199), "Consumer Staples"), ((2200, 2399), "Consumer Discretionary"),
    ((2400, 2799), "Materials"), ((2800, 2829), "Materials"), ((2830, 2836), "Health Care"),
    ((2840, 2899), "Consumer Staples"), ((2900, 2999), "Energy"), ((3000, 3499), "Industrials"),
    ((3500, 3569), "Industrials"), ((3570, 3579), "Information Technology"), ((3580, 3659), "Industrials"),
    ((3660, 3699), "Information Technology"), ((3700, 3799), "Industrials"), ((3800, 3840), "Industrials"),
    ((3841, 3851), "Health Care"), ((3852, 3999), "Consumer Discretionary"), ((4000, 4799), "Industrials"),
    ((4800, 4899), "Communication Services"), ((4900, 4999), "Utilities"), ((5000, 5199), "Industrials"),
    ((5200, 5999), "Consumer Discretionary"), ((6000, 6499), "Financials"), ((6500, 6553), "Real Estate"),
    ((6770, 6799), "Financials"), ((6798, 6798), "Real Estate"), ((7000, 7369), "Consumer Discretionary"),
    ((7370, 7379), "Information Technology"), ((7380, 7999), "Industrials"), ((8000, 8099), "Health Care"),
    ((8100, 8999), "Industrials"),
]

SPEC = {
    "issue": 44, "stage": "RESEARCH",
    "hypothesis": "El Composite de GABI, sin cambios, predice la rentabilidad relativa del trimestre siguiente entre "
                  "las empresas cotizadas de EE. UU. fuera del S&P 500 (IC medio > 0).",
    "why_out_of_sample": "GABI se diseñó con el S&P 500; estas empresas no se usaron para diseñarlo.",
    "universe": {"source": "frames XBRL de SEC (dei:EntityPublicFloat), sin índices de pago",
                 "rule": f"public float fechado en los {feas.LOOKBACK_DAYS} días anteriores, entre "
                         f"{feas.FLOAT_MIN:.0f} y {feas.FLOAT_MAX:.0f} USD; excluidos los emisores del S&P 500 "
                         "en la fecha (identidad acreditada #27/#34)",
                 "dates": f"rebalanceos trimestrales día 2 de {FIRST} a {LAST}"},
    "model": {"weights": scoring.DEFAULT_WEIGHTS, "metrics": scoring.SCORE_METRICS,
              "eligibility": "composite no vacío y cobertura >= 70 % de las 13 métricas (como GABI)",
              "sector": "sector amplio derivado del SIC de SEC (GABI usa fotos de Yahoo que no existen para "
                        "estas empresas); solo afecta al grupo de percentiles",
              "fundamentals": "Company Facts de SEC por CIK, point-in-time por fecha de presentación, con la "
                              "corrección de ejercicios del #38"},
    "prices": {"sources": ["Yahoo (tickers vigentes; serie archivada aparte, sin tocar la caché operativa)",
                           "Tiingo (tickers deslistados)", "Nasdaq Data Link WIKI (hasta 2018-03)"],
               "identity": "ticker por CIK: ticker SEC vigente o declarado en un 10-K/portada XBRL del emisor en el "
                           "intervalo; serie aceptada solo si pasa la comprobación de nivel de precio SEC "
                           "(public float / acciones × cierre, #28)",
               "forward_return": "de la sesión siguiente a la señal a la primera sesión tras +3 meses; si la serie "
                                 "termina antes, último precio (sin evento terminal acreditado: no estricto)"},
    "primary": {"test": "IC de Spearman trimestral entre composite_score y retorno siguiente; media de los "
                        "trimestres; t Newey-West unilateral", "alpha": 0.05},
    "bounds": {"adverse": "elegibles sin retorno siguiente: los de puntuación por encima de la mediana reciben el "
                          "percentil 10 del retorno observado del trimestre y los de debajo el percentil 90",
               "favourable": "el caso simétrico", "complete_case": "solo empresas con retorno"},
    "decision": {"robusta": "IC medio > 0 con p < 0,05 también con la cota adversa",
                 "condicionada_a_los_datos": "p < 0,05 con los casos completos pero no con la cota adversa",
                 "no_concluyente": "IC medio > 0 con p >= 0,05 en los casos completos",
                 "sin_capacidad_predictiva": "IC medio <= 0 en los casos completos"},
    "reporting": ["cobertura por trimestre: universo, con precio, elegibles y sin retorno siguiente",
                  "empresas excluidas por falta de precio, separadas entre las que desaparecen y las que no",
                  "quintiles y Top-20 frente al universo (descriptivos)", "IC por ventana 2011-15, 2016-20, 2021-25"],
    "model_changes": "ninguno; las pruebas ciegas no se tocan",
}


def spec_hash() -> str:
    return hashlib.sha256(json.dumps(SPEC, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def preregister() -> dict:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    path = OUTPUT / "preregistro.json"
    digest = spec_hash()
    if path.exists():
        record = json.loads(path.read_text(encoding="utf-8"))
        if record["sha256"] != digest:
            raise ValueError("La especificación cambió después del preregistro.")
        return record
    experiment = research_lab.log_experiment(
        "gabi_smallmid_ic", "RESEARCH", True, family="stat_4", universe="EE. UU. fuera del S&P 500 (SEC)",
        weights=scoring.DEFAULT_WEIGHTS, rebalance="trimestral día 2", is_start=FIRST, is_end=LAST,
        notes=f"Preregistro #44, sha256 {digest}; sin resultados")
    record = {"sha256": digest, "spec": SPEC, "experiment_id": experiment}
    path.write_text(json.dumps(fs._json_safe(record), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return record


def sector_from_sic(sic) -> str | None:
    try:
        code = int(sic)
    except (TypeError, ValueError):
        return None
    matches = [(hi - lo, name) for (lo, hi), name in SIC_SECTORS if lo <= code <= hi]
    return min(matches)[1] if matches else None  # el rango más específico gana


def rebalance_dates() -> list[str]:
    days, current = [], pd.Timestamp(FIRST)
    while current <= pd.Timestamp(LAST):
        days.append(current.date().isoformat())
        current += pd.DateOffset(months=3)
    return days


def build_universe() -> pd.DataFrame:
    """Universo de cada rebalanceo (datos, no resultados), con la regla preregistrada."""
    WORK.mkdir(parents=True, exist_ok=True)
    path = WORK / "universe.csv"
    if path.exists():
        return pd.read_csv(path, dtype={"cik": str})
    frames = []
    for day in rebalance_dates():
        # La regla usa el último cierre de trimestre previo a la señal.
        anchor = (date.fromisoformat(day) - timedelta(days=2)).isoformat()
        frame = feas.universe(anchor)
        frame.insert(0, "fecha", day)
        frames.append(frame)
        print(day, len(frame), flush=True)
    result = pd.concat(frames, ignore_index=True)
    result.to_csv(path, index=False)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preregister", action="store_true")
    parser.add_argument("--universe", action="store_true")
    parser.add_argument("--tickers", action="store_true")
    parser.add_argument("--levels", action="store_true")
    parser.add_argument("--rankings", action="store_true")
    parser.add_argument("--preregister-a1", action="store_true", help="Ampliación A1 (#47), antes de los rankings")
    parser.add_argument("--kaggle", action="store_true",
                        help="Ampliación A2: importa Kaggle, recalcula comprobaciones, valida y poda la cola")
    parser.add_argument("--preregister-a3", action="store_true", help="Ampliación A3: regla de congelación de datos")
    parser.add_argument("--analyze", action="store_true", help="Solo con los 57 rankings calculados")
    args = parser.parse_args()
    if args.preregister:
        print(json.dumps({"sha256": preregister()["sha256"]}))
    if args.universe:
        frame = build_universe()
        print(json.dumps({"filas": len(frame), "ciks": frame.cik.nunique()}))
    if args.tickers:
        tickers = ticker_map()
        print(tickers.fuente_prevista.value_counts(dropna=False).to_dict())
    if args.levels:
        levels = accepted_series()
        print(levels.groupby("fuente").outcome.value_counts().to_dict())
    if args.rankings:
        rankings()
    if args.preregister_a1:
        print(json.dumps({"sha256": preregister_addendum()["sha256"]}))
    if args.kaggle:
        tickers = ticker_map()
        symbols = set(tickers.ticker_vigente.dropna()) | set(tickers.ticker_10k.dropna())
        report: dict = {"a2": preregister_addendum_a2()["sha256"], "importacion": import_kaggle(symbols)}
        (WORK / "level_checks.csv").unlink(missing_ok=True)  # se recalculan con las cuatro fuentes
        checks = accepted_series()
        report["comprobaciones"] = {f"{source}:{outcome}": int(count) for (source, outcome), count
                                    in checks.groupby("fuente").outcome.value_counts().items()}
        agreement = kaggle_agreement(checks)
        report["concordancia"] = {k: v for k, v in agreement.items() if k != "no_coinciden"}
        if agreement["aceptado"]:
            report["cola_tiingo"] = prune_tiingo_queue(checks)
        print(json.dumps(fs._json_safe(report), ensure_ascii=False, indent=2, default=str))
    if args.preregister_a3:
        print(json.dumps({"sha256": preregister_addendum_a3()["sha256"]}))
    if args.analyze:
        print(json.dumps(fs._json_safe(analyze()), ensure_ascii=False, indent=2))



# --- Etapa 2: ticker por CIK y cola de precios (datos, no resultados) ---------------------------

def ticker_map() -> pd.DataFrame:
    """Ticker candidato de cada empresa del universo y fuente de precios prevista.

    Vivas: ticker vigente de SEC (Yahoo guarda su historia bajo el ticker
    actual). Desaparecidas: símbolo declarado en su último 10-K previo a la
    salida del universo; WIKI si la necesidad acaba antes de 2018-03, Tiingo
    para el resto.
    """
    from . import historical_issuer_evidence as ie
    from . import identity

    path = WORK / "tickers.csv"
    if path.exists():
        return pd.read_csv(path, dtype={"cik": str})
    universe = build_universe()
    spans = universe.groupby("cik").fecha.agg(["min", "max"])
    rows = []
    for number, (cik, span) in enumerate(spans.iterrows(), 1):
        life = ie.listing_life(cik)
        current = [identity.normalize_symbol(t) for t in (life or {}).get("current_tickers", []) if t]
        needed_from = (date.fromisoformat(span["min"]) - timedelta(days=400)).isoformat()
        needed_to = (date.fromisoformat(span["max"]) + timedelta(days=100)).isoformat()
        row = {"cik": cik, "nombre": (life or {}).get("name"), "desde": needed_from, "hasta": needed_to,
               "ticker_vigente": current[0] if current else None, "ticker_10k": None, "fuente_prevista": None}
        if current:
            row["fuente_prevista"] = "yahoo"
        elif life:
            reports = [r for r in life["annual_reports"] if r["filed"] <= needed_to]
            for report in reversed(reports[-2:]):
                try:
                    _url, doc = ie.fetch_annual_report(cik, report)
                except Exception:  # documento no disponible
                    continue
                found = ie.annual_report_symbols(doc.read_text(encoding="utf-8", errors="ignore"), extended=True)
                if len(found) == 1:
                    row["ticker_10k"] = next(iter(found))
                    break
            if row["ticker_10k"]:
                row["fuente_prevista"] = "wiki" if needed_to <= "2018-03-27" else "tiingo"
        rows.append(row)
        if number % 250 == 0:
            print(f"tickers {number}/{len(spans)}", flush=True)
    frame = pd.DataFrame(rows)
    frame.to_csv(path, index=False)
    return frame



# --- Etapa 3: precios archivados (sin tocar la caché operativa) ---------------------------------

YAHOO_SOURCE = "yahoo:smallmid-2026-09"
WIKI_SOURCE = "nasdaq-wiki:frozen-2018-03-27:smallmid"


def fetch_yahoo(symbols: list[str], *, chunk: int = 50) -> dict:
    """Historia diaria de Yahoo con cierre negociado (se deshacen los splits posteriores) y ajustado."""
    import time

    import yfinance as yf

    from . import historical_archive

    historical_archive.register_source(YAHOO_SOURCE, {
        "name": "Yahoo Finance (yfinance), empresas fuera del S&P 500 (#44)", "start": "2009-01-01",
        "end_exclusive": "2026-07-01", "quality": "research_archive_unverified_identity",
        "close_basis": "as_traded: Close de Yahoo multiplicado por los splits posteriores"})
    yf.set_tz_cache_location(str(config.DATA_DIR / "history_refresh" / "yfinance_cache"))
    done_path = WORK / "yahoo_done.txt"
    done = set(done_path.read_text().split()) if done_path.exists() else set()
    counts = {"accepted": 0, "rejected": 0, "empty": 0}
    pending = [s for s in symbols if s not in done]
    for start in range(0, len(pending), chunk):
        batch = pending[start:start + chunk]
        data = yf.download(batch, start="2009-01-01", end="2026-07-01", auto_adjust=False, actions=True,
                           group_by="ticker", progress=False, threads=True)
        for symbol in batch:
            try:
                frame = data[symbol] if len(batch) > 1 else data
            except KeyError:
                counts["empty"] += 1
                continue
            frame = frame.dropna(subset=["Close", "Adj Close"])
            if frame.empty:
                counts["empty"] += 1
                continue
            splits = frame.get("Stock Splits", pd.Series(0.0, index=frame.index)).fillna(0.0)
            factor = pd.Series(1.0, index=frame.index)
            for day, ratio in splits[splits > 0].items():
                factor[factor.index < day] *= float(ratio)
            chunk_frame = pd.DataFrame({
                "symbol": symbol, "date": frame.index.strftime("%Y-%m-%d"), "open": frame["Open"] * factor,
                "high": frame["High"] * factor, "low": frame["Low"] * factor, "close": frame["Close"] * factor,
                "adjusted_close": frame["Adj Close"], "volume": frame["Volume"]})
            result = historical_archive.import_price_chunk(YAHOO_SOURCE, chunk_frame, {symbol}, "2009-01-01",
                                                           "2026-07-01")
            counts["accepted"] += result["accepted"]
            counts["rejected"] += result["rejected"]
        done |= set(batch)
        done_path.write_text("\n".join(sorted(done)))
        print(f"yahoo {min(start + chunk, len(pending))}/{len(pending)} {counts}", flush=True)
        time.sleep(2)
    return counts


def fetch_wiki(requests_list: list[tuple[str, str, str]]) -> dict:
    """WIKI por ticker y ventana (hasta 2018-03), en una fuente propia para no alterar la del #28."""
    import time

    import requests

    from . import historical_archive
    from . import historical_wiki as wiki

    key = config.load_nasdaq_data_link_key()
    if not key:
        raise ValueError("Falta la clave de Nasdaq Data Link (Configuración)")
    historical_archive.register_source(WIKI_SOURCE, {
        "name": "Nasdaq Data Link WIKI Prices (community, frozen 2018-03-27), fuera del S&P 500 (#44)",
        "url": wiki.URL, "start": "2009-01-01", "end_exclusive": "2018-03-28",
        "quality": "research_archive_unverified_identity"})
    directory = WORK / "wiki"
    directory.mkdir(parents=True, exist_ok=True)
    counts = {"fetched": 0, "cached": 0, "empty": 0}
    for symbol, first, last in requests_list:
        path = directory / f"{symbol}.json"
        if not path.exists():
            params = {"ticker": wiki._wiki_ticker(symbol), "date.gte": first, "date.lt": min(last, "2018-03-28"),
                      "qopts.columns": "ticker,date,open,high,low,close,volume,adj_close", "api_key": key}
            response = None
            for attempt in range(5):
                try:
                    response = requests.get(wiki.URL, params=params, timeout=120)
                except requests.RequestException:
                    time.sleep(30 * (attempt + 1))  # corte o tiempo agotado: reintentar
                    continue
                if response.status_code in (429, 500, 502, 503, 504):
                    time.sleep(60 * (attempt + 1))
                    continue
                break
            if response is None or response.status_code != 200:
                counts["failed"] = counts.get("failed", 0) + 1
                continue
            payload = response.json()["datatable"]
            path.write_text(json.dumps({"columns": [c["name"] for c in payload["columns"]], "data": payload["data"]}),
                            encoding="utf-8")
            counts["fetched"] += 1
            time.sleep(0.3)
        else:
            counts["cached"] += 1
        stored = json.loads(path.read_text(encoding="utf-8"))
        frame = pd.DataFrame(stored["data"], columns=stored["columns"])
        if frame.empty:
            counts["empty"] += 1
            continue
        frame = frame.rename(columns={"adj_close": "adjusted_close"}).assign(symbol=symbol)
        historical_archive.import_price_chunk(WIKI_SOURCE, frame, {symbol}, "2009-01-01", "2018-03-28")
    return counts


# --- Etapa 3b (ampliación A2): precios de Kaggle para las desaparecidas hasta 2021 ---------------

KAGGLE_SOURCE = "kaggle:tsaustin-us-prices-2021-06:smallmid"
KAGGLE_ZIP = config.DATA_DIR / "kaggle" / "archive (3).zip"
KAGGLE_MEMBER = "stocks_latest/stock_prices_latest.csv"
KAGGLE_CUTOFF = "2021-06-01"  # el conjunto se corta aquí; una serie que acaba ahí no es una empresa desaparecida
KAGGLE_LAST_REBALANCE = "2021-01-02"  # último rebalanceo cuyo trimestre siguiente termina antes del corte
AGREEMENT_MIN = 0.90
KAGGLE_URL = "https://www.kaggle.com/datasets/tsaustin/us-historical-stock-prices-with-earnings-data"

ADDENDUM_A2 = {
    "issue": 44, "amends": "preregistro #44 y ampliación A1", "stage": "RESEARCH",
    "motivation": "Tiingo gratuito tarda meses y FMP gratuito no sirve deslistadas; un conjunto público de Kaggle "
                  "(US historical stock prices with earnings data, tsaustin, NASDAQ/NYSE/AMEX 1998-2021-06) cubre "
                  "muchas empresas desaparecidas entre 2018 y 2021. Se añade antes de calcular ningún ranking.",
    "source": {"id": KAGGLE_SOURCE, "url": KAGGLE_URL,
               "file": KAGGLE_MEMBER,
               "fields": "close negociado (as traded), close_adjusted (splits y dividendos), split_coefficient"},
    "cleaning": ["filas con algún precio <= 0 o OHLC incoherente: rechazadas por el importador (igual que el resto)",
                 "picos de un día que se deshacen: |r_t| > 50 % y |r_t+1| > 33 % de signo contrario; se elimina el "
                 "día t"],
    "validation": {"level_check": "cada serie solo se acepta con la comprobación de nivel de precio SEC (#28), la "
                                  "misma regla de 400 días que las demás fuentes",
                   "dataset_agreement": f"entre las empresas (CIK) con serie de Kaggle y de otra fuente que pasan "
                                        f"ambas la comprobación SEC, al menos el {AGREEMENT_MIN:.0%} deben coincidir "
                                        "(cierre con diferencia mediana < 1 % y menos del 2 % de días con retornos "
                                        "distintos en más de 1 punto); si no, Kaggle no se usa en absoluto"},
    "priority": "Yahoo, Tiingo, WIKI y por último Kaggle",
    "cutoff": f"solo rebalanceos hasta {KAGGLE_LAST_REBALANCE}: el trimestre siguiente debe terminar antes de "
              f"{KAGGLE_CUTOFF}, donde se corta el conjunto",
    "analysis": "sin cambios: las funciones del análisis de A1 conservan su huella "
                "69efba582a6ca0f9b09fde77a7d710225a577bfd814512030238ea94f9af4538",
    "tiingo_queue": "se retiran de la cola de Tiingo los símbolos cuyas empresas quedan cubiertas en todas sus "
                    "fechas del universo; la cola original se conserva",
    "data_state_rule": "se preregistra solo si no existe ningún ranking del #44",
}


def addendum_a2_hash() -> str:
    return hashlib.sha256(json.dumps(ADDENDUM_A2, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def preregister_addendum_a2() -> dict:
    """Ampliación A2 con hash; se niega si ya hay algún ranking del #44 calculado."""
    path = OUTPUT / "preregistro-a2.json"
    digest = addendum_a2_hash()
    if path.exists():
        record = json.loads(path.read_text(encoding="utf-8"))
        if record["sha256"] != digest:
            raise ValueError("La ampliación A2 cambió después de preregistrarse.")
        return record
    computed = sorted((WORK / "rankings").glob("ranking-*.csv"))
    if computed:
        raise ValueError(f"Ya hay {len(computed)} rankings del #44: la ampliación no sería previa a los datos.")
    base, first = preregister(), preregister_addendum()
    experiment = research_lab.log_experiment(
        "gabi_smallmid_kaggle_source", "RESEARCH", True, family="stat_4",
        universe="EE. UU. fuera del S&P 500 (SEC)", weights=scoring.DEFAULT_WEIGHTS, rebalance="trimestral día 2",
        is_start=FIRST, is_end=LAST,
        notes=f"Ampliación A2 (fuente Kaggle) de {base['sha256']} y A1 {first['sha256']}; sha256 {digest}; sin "
              "rankings ni resultados")
    record = {"sha256": digest, "amends_sha256": [base["sha256"], first["sha256"]], "addendum": ADDENDUM_A2,
              "code_sha256": fs.content_hash(Path(__file__)), "experiment_id": experiment,
              "rankings_at_registration": 0}
    path.write_text(json.dumps(fs._json_safe(record), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return record


def clean_kaggle(frame: pd.DataFrame) -> pd.DataFrame:
    """Quita los picos de un día que se deshacen (regla A2); el importador rechaza el resto."""
    frame = frame.sort_values(["symbol", "date"])
    grouped = frame.groupby("symbol").close_adjusted
    change = grouped.pct_change()
    following = change.groupby(frame.symbol).shift(-1)
    spike = (change.abs() > 0.5) & (following.abs() > 1 / 3) & ((change > 0) != (following > 0))
    return frame[~spike]


def import_kaggle(symbols: set[str]) -> dict:
    """Importa del zip de Kaggle solo los símbolos del universo, como fuente archivada propia."""
    import zipfile

    from . import historical_archive

    preregister_addendum_a2()
    historical_archive.register_source(KAGGLE_SOURCE, {
        "name": "Kaggle: US historical stock prices with earnings data (tsaustin), fuera del S&P 500 (#44)",
        "url": KAGGLE_URL, "start": "2009-01-01", "end_exclusive": KAGGLE_CUTOFF,
        "quality": "research_archive_unverified_identity",
        "files_sha256": {KAGGLE_ZIP.name: hashlib.sha256(KAGGLE_ZIP.read_bytes()).hexdigest()}})
    parts = []
    with zipfile.ZipFile(KAGGLE_ZIP) as archive, archive.open(KAGGLE_MEMBER) as stream:
        for chunk in pd.read_csv(stream, chunksize=2_000_000, dtype={"symbol": str}):
            parts.append(chunk[chunk.symbol.isin(symbols)])
    raw = pd.concat(parts)
    cleaned = clean_kaggle(raw)
    counts = {"filas": len(raw), "picos_eliminados": len(raw) - len(cleaned), "accepted": 0, "rejected": 0}
    for symbol, frame in cleaned.groupby("symbol"):
        chunk = frame.rename(columns={"close_adjusted": "adjusted_close"})[
            ["symbol", "date", "open", "high", "low", "close", "adjusted_close", "volume"]]
        result = historical_archive.import_price_chunk(KAGGLE_SOURCE, chunk, {symbol}, "2009-01-01", KAGGLE_CUTOFF)
        counts["accepted"] += result["accepted"]
        counts["rejected"] += result["rejected"]
    return counts


def series_agree(reference: pd.DataFrame, candidate: pd.DataFrame) -> dict | None:
    """Concordancia de dos series de la misma empresa en sus días comunes (None si hay menos de 60)."""
    common = reference.index.intersection(candidate.index)
    if len(common) < 60:
        return None
    a, b = reference.loc[common], candidate.loc[common]
    close_diff = float((b.close / a.close - 1).abs().median())
    mismatch = float(((a.adj_close.pct_change() - b.adj_close.pct_change()).abs().dropna() > 0.01).mean())
    return {"dias": len(common), "dif_cierre_mediana": close_diff, "dias_retorno_distinto": mismatch,
            "coincide": close_diff < 0.01 and mismatch < 0.02}


def kaggle_agreement(checks: pd.DataFrame) -> dict:
    """Validación del conjunto (A2): concordancia con otras fuentes cuando ambas pasan la comprobación SEC."""
    passed = checks[checks.outcome == "passed"][["cik", "fuente", "simbolo"]].drop_duplicates()
    sources = _sources()
    rows = []
    for cik, group in passed.groupby("cik"):
        kaggle = group[group.fuente == "kaggle"]
        others = group[group.fuente != "kaggle"]
        if kaggle.empty or others.empty:
            continue
        candidate = _series(KAGGLE_SOURCE, kaggle.simbolo.iloc[0])
        for other in others.itertuples():
            result = series_agree(_series(sources[other.fuente], other.simbolo), candidate)
            if result:
                rows.append({"cik": cik, "fuente": other.fuente, **result})
    frame = pd.DataFrame(rows)
    share = float(frame.coincide.mean()) if len(frame) else 0.0
    report = {"comparaciones": len(frame), "empresas": int(frame.cik.nunique()) if len(frame) else 0,
              "coinciden": share, "minimo": AGREEMENT_MIN, "aceptado": bool(len(frame) >= 30 and share >= AGREEMENT_MIN),
              "no_coinciden": frame[~frame.coincide].to_dict("records") if len(frame) else []}
    (WORK / "kaggle_agreement.json").write_text(json.dumps(fs._json_safe(report), ensure_ascii=False, indent=1))
    kaggle_accepted.cache_clear()
    return report


@functools.cache
def kaggle_accepted() -> bool:
    path = WORK / "kaggle_agreement.json"
    return path.exists() and bool(json.loads(path.read_text(encoding="utf-8"))["aceptado"])


def prune_tiingo_queue(checks: pd.DataFrame) -> dict:
    """Retira de la cola de Tiingo los símbolos pendientes cuyas empresas ya tienen serie aceptada en todas sus
    fechas del universo. La cola original se guarda en ``tiingo_symbols.before_a2.txt``."""
    from . import historical_tiingo

    queue_path = WORK / "tiingo_symbols.txt"
    backup = WORK / "tiingo_symbols.before_a2.txt"
    if not backup.exists():
        backup.write_text(queue_path.read_text())
    queue = [s.strip().upper() for s in backup.read_text().split() if s.strip()]
    done = {p.stem for p in historical_tiingo._window("smallmid")[3].glob("*.json")}
    tickers = ticker_map()
    symbol_of = tickers.ticker_vigente.where(tickers.ticker_vigente.notna(), tickers.ticker_10k)
    ciks_of = tickers.groupby(symbol_of).cik.apply(list).to_dict()
    universe = build_universe()
    dates_of = universe.groupby("cik").fecha.apply(list).to_dict()
    kept: list[str] = []
    removed: list[str] = []
    for symbol in queue:
        covered = symbol not in done and all(usable(checks, cik, day) for cik in ciks_of.get(symbol, [])
                                             for day in dates_of.get(cik, []))
        (removed if covered and ciks_of.get(symbol) else kept).append(symbol)
    queue_path.write_text("\n".join(kept) + "\n")
    return {"cola_original": len(queue), "retirados": len(removed), "cola_nueva": len(kept),
            "pendientes_nuevos": sum(s not in done for s in kept)}


# --- Ampliación A3: cuándo se da por cerrada la recogida de datos ---------------------------------

DATA_FREEZE_DEADLINE = "2027-01-15"

ADDENDUM_A3 = {
    "issue": 44, "amends": "preregistro #44 y ampliaciones A1 y A2", "stage": "RESEARCH",
    "motivation": "Sin una fecha fijada de antemano, esperar a 'un poco más de datos' puede acabar decidiéndose por "
                  "cómo pintan los resultados. Se fija ahora, sin rankings ni resultados.",
    "freeze_rule": f"los datos se congelan cuando una ejecución de Tiingo recorre la cola entera sin detenerse por el "
                   f"cupo, o el {DATA_FREEZE_DEADLINE}, lo que ocurra antes; se analiza con la cobertura que haya "
                   "entonces, con las cotas preregistradas",
    "order": "congelación, rankings de las 57 fechas, retornos siguientes y análisis, una sola vez",
    "no_further_sources": "tras la congelación no se añaden fuentes ni se repite el análisis con más datos",
    "data_state_rule": "se preregistra solo si no existe ningún ranking del #44",
}


def addendum_a3_hash() -> str:
    return hashlib.sha256(json.dumps(ADDENDUM_A3, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def preregister_addendum_a3() -> dict:
    """Ampliación A3 con hash; se niega si ya hay algún ranking del #44 calculado."""
    path = OUTPUT / "preregistro-a3.json"
    digest = addendum_a3_hash()
    if path.exists():
        record = json.loads(path.read_text(encoding="utf-8"))
        if record["sha256"] != digest:
            raise ValueError("La ampliación A3 cambió después de preregistrarse.")
        return record
    computed = sorted((WORK / "rankings").glob("ranking-*.csv"))
    if computed:
        raise ValueError(f"Ya hay {len(computed)} rankings del #44: la ampliación no sería previa a los datos.")
    amended = [preregister()["sha256"], preregister_addendum()["sha256"], preregister_addendum_a2()["sha256"]]
    experiment = research_lab.log_experiment(
        "gabi_smallmid_data_freeze", "RESEARCH", True, family="stat_4", universe="EE. UU. fuera del S&P 500 (SEC)",
        weights=scoring.DEFAULT_WEIGHTS, rebalance="trimestral día 2", is_start=FIRST, is_end=LAST,
        notes=f"Ampliación A3 (congelación de datos) de {amended}; sha256 {digest}; sin rankings ni resultados")
    record = {"sha256": digest, "amends_sha256": amended, "addendum": ADDENDUM_A3,
              "code_sha256": fs.content_hash(Path(__file__)), "experiment_id": experiment,
              "rankings_at_registration": 0}
    path.write_text(json.dumps(fs._json_safe(record), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return record


def tiingo_complete_path() -> Path:
    return WORK / "tiingo_completa.json"


def mark_tiingo_complete(report: dict) -> None:
    """Lo llama la tarea de Tiingo cuando recorre la cola sin detenerse por el cupo (regla A3)."""
    if "stopped_at" in report:
        return
    path = tiingo_complete_path()
    if not path.exists():
        path.write_text(json.dumps({"fecha": date.today().isoformat(), "descarga": report}, indent=1))


def data_frozen(today: date | None = None) -> bool:
    return tiingo_complete_path().exists() or (today or date.today()).isoformat() >= DATA_FREEZE_DEADLINE


def result_path() -> Path:
    return OUTPUT / "resultado.json"


def final_run() -> dict:
    """Paso final de A3, una sola vez: importa lo descargado, recalcula las comprobaciones, rankings y análisis.

    Lo lanza ``periodic_tasks --run`` en cuanto los datos se congelan; si se interrumpe, se reanuda donde quedó.
    """
    from . import historical_tiingo
    _require_frozen()
    if result_path().exists():
        return {"omitido": "el #44 ya está analizado"}
    report: dict = {"tiingo": historical_tiingo.import_cached("smallmid")}
    if not any((WORK / "rankings").glob("ranking-*.csv")):
        (WORK / "level_checks.csv").unlink(missing_ok=True)  # comprobaciones con todos los datos congelados
    checks = accepted_series()
    agreement = kaggle_agreement(checks)
    report["kaggle_aceptado"] = agreement["aceptado"]
    rankings()
    result = analyze()
    report.update(decision_principal=result["decision_principal"], decision_a1=result["decision_a1"])
    return report


def _require_frozen() -> None:
    preregister_addendum_a3()
    if not data_frozen():
        raise ValueError(f"Datos sin congelar (A3): falta completar la cola de Tiingo o llegar al "
                         f"{DATA_FREEZE_DEADLINE}.")


# --- Etapa 4: series aceptadas (comprobación de nivel de precio SEC, #28) ------------------------

def _tiingo_source() -> str:
    from . import historical_tiingo
    return historical_tiingo.source_id("smallmid")


def _sources() -> dict[str, str]:
    return {"yahoo": YAHOO_SOURCE, "wiki": WIKI_SOURCE, "tiingo": _tiingo_source(), "kaggle": KAGGLE_SOURCE}


def _series(source_id: str, symbol: str) -> pd.DataFrame:
    from . import storage
    with storage.get_connection() as conn:
        frame = pd.read_sql_query("SELECT date,close,adj_close FROM historical_prices WHERE source_id=? AND symbol=? "
                                  "ORDER BY date", conn, params=(source_id, symbol))
    frame.index = pd.to_datetime(frame.pop("date"))
    return frame[(frame.close > 0) & (frame.adj_close > 0)]


def accepted_series() -> pd.DataFrame:
    """Por empresa y fuente, las fechas de float cuya comprobación de nivel pasa o falla.

    Una serie sirve para un rebalanceo si en los 400 días anteriores hay al
    menos una comprobación superada y ninguna fallida (regla preregistrada).
    """
    from . import historical_issuer_evidence as ie
    from .historical_price_audit import _split_ratios

    path = WORK / "level_checks.csv"
    if path.exists():
        return pd.read_csv(path, dtype={"cik": str})
    tickers = ticker_map()
    sources = _sources()
    rows = []
    for number, row in enumerate(tickers.itertuples(index=False), 1):
        symbol = row.ticker_vigente if isinstance(row.ticker_vigente, str) else row.ticker_10k
        if not isinstance(symbol, str):
            continue
        facts = ie.issuer_facts(row.cik)
        for name in sources:
            frame = _series(sources[name], symbol)
            if len(frame) < 60:
                continue
            start, end = frame.index[0].date().isoformat(), frame.index[-1].date().isoformat()
            checks = ie.price_level_checks(facts, frame["close"], start, end, splits=_split_ratios(frame))
            for check in checks:
                rows.append({"cik": row.cik, "fuente": name, "simbolo": symbol, "desde": start, "hasta": end,
                             "float_date": check["float_date"], "outcome": check["outcome"],
                             "ratio": check.get("ratio")})
            if not checks:
                rows.append({"cik": row.cik, "fuente": name, "simbolo": symbol, "desde": start, "hasta": end,
                             "float_date": None, "outcome": "missing", "ratio": None})
        if number % 500 == 0:
            print(f"nivel {number}/{len(tickers)}", flush=True)
    frame = pd.DataFrame(rows)
    frame.to_csv(path, index=False)
    return frame


def usable(checks: pd.DataFrame, cik: str, day: str) -> tuple[str, str] | None:
    """(fuente, símbolo) aceptado para ``day`` o None.

    Prioridad Yahoo, Tiingo, WIKI y, por la ampliación A2, Kaggle: solo si el
    conjunto superó la validación de concordancia y hasta KAGGLE_LAST_REBALANCE.
    """
    low = (date.fromisoformat(day) - timedelta(days=400)).isoformat()
    candidates = checks[(checks.cik == cik) & (checks.desde <= low) & (checks.hasta >= day)]
    names = ["yahoo", "tiingo", "wiki"]
    if day <= KAGGLE_LAST_REBALANCE and kaggle_accepted():
        names.append("kaggle")
    for name in names:
        own = candidates[candidates.fuente == name]
        window = own[(own.float_date >= low) & (own.float_date <= day)]
        if len(window) and (window.outcome == "passed").any() and not (window.outcome == "failed").any():
            return name, str(own.simbolo.iloc[0])
    return None


# --- Etapa 5: rankings con el motor de GABI, sin cambios --------------------------------------

def rankings() -> None:
    """Ranking completo de cada rebalanceo con ``screener_asof.build_ranking_as_of``.

    Solo se sustituyen las fuentes: universo (SEC), identidad (CIK), serie de
    precios aceptada y sector (SIC). Pesos, métricas, filtro de cobertura y
    la corrección #38 son los de GABI. Los rankings se guardan con hash; el
    análisis preregistrado no se ejecuta hasta tener todos los datos.
    """
    import hashlib as _hashlib
    from unittest.mock import patch

    from . import edgar, entity_master, historical_pit, identity, screener_asof
    from . import historical_issuer_evidence as ie

    _require_frozen()
    universe = build_universe()
    checks = accepted_series()
    sources = _sources()
    sics: dict[str, str | None] = {}
    for cik in universe.cik.unique():
        path = ie.SUBMISSIONS_DIR / f"CIK{cik}.json"
        sics[cik] = sector_from_sic(json.loads(path.read_text(encoding="utf-8")).get("sic")) if path.exists() else None
    directory = WORK / "rankings"
    directory.mkdir(parents=True, exist_ok=True)
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"spec_sha256": spec_hash()}
    for day in rebalance_dates():
        if day in manifest:
            continue
        members = universe[universe.fecha == day].cik.tolist()
        chosen = {cik: usable(checks, cik, day) for cik in members}
        symbols = [f"C{cik}" for cik in members]

        def resolve(symbol, as_of, **_):
            cik = symbol[1:]
            return {"entity_id": f"cik:{cik}", "cik": cik, "status": "resolved", "candidates": [f"cik:{cik}"],
                    "source": "sec_float_universe", "confidence": 1.0}

        def price_history(symbol, as_of, *, entity_id=None, chosen=chosen):
            choice = chosen.get(symbol[1:])
            if not choice:
                return pd.DataFrame(columns=["close", "adj_close"])
            frame = _series(sources[choice[0]], choice[1])
            frame = frame[frame.index <= pd.Timestamp(as_of)]
            frame.attrs.update(source_id=sources[choice[0]], source_symbol=choice[1])
            return frame

        def sector_asof(symbols_, as_of, **_):
            return {s: {"sector": sics.get(s[1:]), "industry": None, "name": None, "cik": s[1:],
                        "effective_date": None, "is_approximate": True} for s in symbols_}

        with (historical_pit.accredited_periods(), edgar.fiscal_alignment(True),
              patch.object(identity, "resolve", resolve), patch.object(identity, "price_history", price_history),
              patch.object(entity_master, "get_sector_asof", sector_asof)):
            table = screener_asof.build_ranking_as_of(day, symbols=symbols)["table"]
        table["precio_fuente"] = [(chosen.get(s[1:]) or (None, None))[0] for s in table.index]
        out = directory / f"ranking-{day}.csv"
        table.to_csv(out)
        manifest[day] = {"sha256": _hashlib.sha256(out.read_bytes()).hexdigest(), "miembros": len(members),
                         "con_precio": sum(bool(v) for v in chosen.values())}
        manifest_path.write_text(json.dumps(manifest, indent=1))
        print(day, manifest[day], flush=True)


# --- Ampliación A1 (#47): ¿la señal está solo en la parte alta del ranking? -----------------------
# Escrita antes de calcular ningún ranking del #44. El análisis de abajo (principal y A1) queda
# congelado aquí, con su hash, antes de ver ningún retorno.

BANDS = [(0.00, 0.01), (0.01, 0.05), (0.05, 0.10), (0.10, 0.20), (0.20, 0.40), (0.40, 0.60), (0.60, 0.80),
         (0.80, 1.00)]
TAIL_ALPHA = 0.05
WINDOWS = {"2011-15": ("2011-07-02", "2016-01-01"), "2016-20": ("2016-01-01", "2021-01-01"),
           "2021-25": ("2021-01-01", "2025-07-03")}

ADDENDUM_A1 = {
    "issue": 47, "amends": 44, "stage": "RESEARCH",
    "motivation": "En el S&P 500 (#40) el Composite no ordena el universo (IC 0,009, t 0,66) pero el Top-20 superó "
                  "al universo elegible en +1,36 pp/trimestre (t 3,93). Ese resultado ya se vio y no es evidencia; "
                  "la hipótesis de que la señal vive solo en la parte alta se contrasta aquí, con datos no usados.",
    "hypothesis": "Las empresas de la parte alta del ranking de GABI superan, en el trimestre siguiente, a la media "
                  "equiponderada de las elegibles de ese trimestre, fuera del S&P 500.",
    "tests": {"t1_top20": "retorno medio equiponderado de las 20 elegibles con mayor composite menos la media de "
                          "todas las elegibles; serie trimestral; media con t Newey-West unilateral",
              "t2_top5pct": "igual con el 5 % superior de las elegibles (redondeo hacia arriba); 20 de unas 450 "
                            "elegibles del S&P 500 es el 4,4 %: la versión proporcional de T1"},
    "multiplicity": f"Holm sobre T1 y T2 con alfa de familia {TAIL_ALPHA}; familia separada de la prueba principal "
                    "del #44, que no cambia",
    "bounds": "las mismas cotas del preregistro del #44 (adversa, favorable y casos completos) aplicadas a las "
              "elegibles sin retorno siguiente antes de calcular T1 y T2",
    "decision": {"cola_robusta": "T1 o T2 con media > 0 y p Holm < 0,05 con la cota adversa y con casos completos",
                 "cola_condicionada_a_los_datos": "T1 o T2 con p Holm < 0,05 en casos completos, no con la adversa",
                 "cola_no_concluyente": "medias de T1 y T2 > 0 en casos completos sin p Holm < 0,05",
                 "sin_efecto_de_cola": "media de T1 o T2 <= 0 en casos completos, sin ninguna significativa"},
    "descriptive": {"bands": [f"{a:.0%}-{b:.0%}" for a, b in BANDS],
                    "band_metric": "exceso medio trimestral de cada banda frente a la media de elegibles",
                    "convexity": "banda 0-5 % menos banda 5-20 %, con t Newey-West, solo descriptiva",
                    "windows": list(WINDOWS), "top20_turnover": True},
    "gross_returns": "retornos brutos sin costes: una cola significativa no implica que sea invertible",
    "model_changes": "ninguno; no se cambian pesos ni el modelo Investor por esta prueba",
    "data_state_rule": "se preregistra solo si no existe ningún ranking del #44",
}


def addendum_hash() -> str:
    return hashlib.sha256(json.dumps(ADDENDUM_A1, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def preregister_addendum() -> dict:
    """Ampliación A1 con hash; se niega si ya hay algún ranking del #44 calculado."""
    path = OUTPUT / "preregistro-a1.json"
    digest = addendum_hash()
    if path.exists():
        record = json.loads(path.read_text(encoding="utf-8"))
        if record["sha256"] != digest:
            raise ValueError("La ampliación A1 cambió después de preregistrarse.")
        return record
    computed = sorted((WORK / "rankings").glob("ranking-*.csv"))
    if computed:
        raise ValueError(f"Ya hay {len(computed)} rankings del #44: la ampliación no sería previa a los datos.")
    base = preregister()
    experiment = research_lab.log_experiment(
        "gabi_smallmid_tail", "RESEARCH", True, family="stat_4", universe="EE. UU. fuera del S&P 500 (SEC)",
        weights=scoring.DEFAULT_WEIGHTS, rebalance="trimestral día 2", is_start=FIRST, is_end=LAST,
        notes=f"Ampliación A1 (#47) del preregistro #44 {base['sha256']}; sha256 {digest}; sin rankings ni "
              "resultados")
    record = {"sha256": digest, "amends_sha256": base["sha256"], "addendum": ADDENDUM_A1,
              "analysis_code_sha256": fs.content_hash(Path(__file__)), "experiment_id": experiment,
              "rankings_at_registration": 0}
    path.write_text(json.dumps(fs._json_safe(record), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return record


# --- Etapa 6: retornos siguientes y análisis preregistrado ------------------------------------

def forward_return(frame: pd.DataFrame, day: str) -> tuple[float | None, bool]:
    """(retorno, termina_antes) según el preregistro: de la sesión siguiente a la señal a la primera sesión
    tras +3 meses; si la serie termina antes, último precio."""
    import exchange_calendars as xcals
    calendar = xcals.get_calendar("XNYS")
    signal = calendar.date_to_session(pd.Timestamp(day), direction="previous")
    entry = calendar.next_session(signal)
    exit_session = calendar.date_to_session(pd.Timestamp(day) + pd.DateOffset(months=3), direction="next")
    prices = frame["adj_close"].dropna()
    after_entry = prices[prices.index >= entry]
    if after_entry.empty or after_entry.index[0] > entry + pd.Timedelta(days=7):
        return None, True
    after_exit = prices[prices.index >= exit_session]
    if len(after_exit):
        return float(after_exit.iloc[0] / after_entry.iloc[0] - 1), False
    if prices.index[-1] <= after_entry.index[0]:
        return None, True
    return float(prices.iloc[-1] / after_entry.iloc[0] - 1), True


def forward_returns() -> dict:
    """Retorno siguiente de cada elegible de cada ranking (datos, no resultados)."""
    checks = accepted_series()
    sources = _sources()
    directory = WORK / "rankings"
    report = {}
    for day in rebalance_dates():
        path = directory / f"forward-{day}.csv"
        if not path.exists():
            table = pd.read_csv(directory / f"ranking-{day}.csv", index_col=0)
            eligible = table.index[table["composite_score"].notna() & (table["score_coverage"] >= 0.7)]
            rows = []
            for symbol in eligible:
                choice = usable(checks, symbol[1:], day)
                value, ends = forward_return(_series(sources[choice[0]], choice[1]), day) if choice else (None, True)
                rows.append({"symbol": symbol, "retorno": value, "termina_antes": ends})
            pd.DataFrame(rows, columns=["symbol", "retorno", "termina_antes"]).set_index("symbol").to_csv(path)
        frame = pd.read_csv(path, index_col=0)
        report[day] = {"elegibles": len(frame), "con_retorno": int(frame.retorno.notna().sum()),
                       "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    (directory / "forward-manifest.json").write_text(json.dumps(report, indent=1))
    return report


def apply_bound(frame: pd.DataFrame, kind: str) -> pd.DataFrame:
    """Cotas preregistradas para las elegibles sin retorno siguiente."""
    frame = frame.dropna(subset=["composite_score"])
    if kind == "casos_completos":
        return frame.dropna(subset=["retorno"])
    observed = frame.retorno.dropna()
    low, high = observed.quantile(0.10), observed.quantile(0.90)
    above = frame.composite_score > frame.composite_score.median()
    good, bad = (low, high) if kind == "favorable" else (high, low)
    fill = pd.Series(good, index=frame.index).where(~above, bad)
    return frame.assign(retorno=frame.retorno.fillna(fill))


def quarter_stats(frame: pd.DataFrame) -> dict:
    """IC y excesos de la parte alta y de cada banda frente a la media de elegibles de un trimestre."""
    import math

    from scipy import stats
    ordered = frame.sort_values("composite_score", ascending=False)
    n, mean = len(ordered), float(ordered.retorno.mean())
    row: dict[str, float | None] = {"n": n, "ic": float(stats.spearmanr(ordered.composite_score, ordered.retorno).statistic),
           "t1_top20": float(ordered.retorno.iloc[:20].mean() - mean),
           "t2_top5pct": float(ordered.retorno.iloc[:math.ceil(0.05 * n)].mean() - mean)}
    for a, b in BANDS:
        band = ordered.retorno.iloc[int(round(a * n)):int(round(b * n))]
        row[f"banda_{a:.0%}-{b:.0%}"] = float(band.mean() - mean) if len(band) else None
    head = ordered.retorno.iloc[:int(round(0.05 * n))]
    middle = ordered.retorno.iloc[int(round(0.05 * n)):int(round(0.20 * n))]
    row["convexidad"] = float(head.mean() - middle.mean()) if len(head) and len(middle) else None
    return row


def _nw(values: pd.Series) -> dict:
    from .cross_section_test import _nw as nw
    return nw(values)


def holm(pvalues: dict[str, float]) -> dict[str, float]:
    ordered, running, adjusted = sorted(pvalues, key=lambda k: pvalues[k]), 0.0, {}
    for rank, key in enumerate(ordered):
        running = max(running, min(1.0, (len(ordered) - rank) * pvalues[key]))
        adjusted[key] = running
    return adjusted


def decide_primary(ic: dict[str, dict]) -> str:
    complete, adverse = ic["casos_completos"], ic["adversa"]
    if complete["media"] <= 0:
        return "sin_capacidad_predictiva"
    if complete["p_unilateral"] >= 0.05:
        return "no_concluyente"
    return "robusta" if adverse["media"] > 0 and adverse["p_unilateral"] < 0.05 else "condicionada_a_los_datos"


def decide_tail(tail: dict[str, dict]) -> str:
    def significant(bound):
        return any(tail[bound][t]["media"] > 0 and tail[bound][t]["p_holm"] < TAIL_ALPHA
                   for t in ("t1_top20", "t2_top5pct"))
    if significant("casos_completos"):
        return "cola_robusta" if significant("adversa") else "cola_condicionada_a_los_datos"
    if all(tail["casos_completos"][t]["media"] > 0 for t in ("t1_top20", "t2_top5pct")):
        return "cola_no_concluyente"
    return "sin_efecto_de_cola"


def analyze_panels(panels: dict[str, pd.DataFrame]) -> dict:
    """Pruebas preregistradas sobre los paneles trimestrales de cada cota (columna ``fecha``)."""
    ic, tail = {}, {}
    for bound, panel in panels.items():
        ic[bound] = _nw(panel.ic)
        tests = {t: _nw(panel[t]) for t in ("t1_top20", "t2_top5pct")}
        for key, value in holm({t: v["p_unilateral"] for t, v in tests.items()}).items():
            tests[key]["p_holm"] = value
        tail[bound] = tests
    complete = panels["casos_completos"]
    bands = [c for c in complete if c.startswith("banda_")]
    return {"principal_ic": ic, "decision_principal": decide_primary(ic), "a1_cola": tail,
            "decision_a1": decide_tail(tail),
            "descriptivas": {"bandas": {c: _nw(complete[c]) for c in bands}, "convexidad": _nw(complete.convexidad),
                             "ic_por_ventana": {name: _nw(complete[(complete.fecha >= a) & (complete.fecha < b)].ic)
                                                for name, (a, b) in WINDOWS.items()}}}


def analyze() -> dict:
    """Análisis final. Solo con los 57 rankings calculados (tras completar la cola de Tiingo)."""
    _require_frozen()
    base, addendum = preregister(), preregister_addendum()
    directory = WORK / "rankings"
    missing = [d for d in rebalance_dates() if not (directory / f"ranking-{d}.csv").exists()]
    if missing:
        raise ValueError(f"Faltan {len(missing)} rankings; el análisis espera a tener todos los datos.")
    forward_returns()
    rows: dict[str, list[dict]] = {"adversa": [], "favorable": [], "casos_completos": []}
    coverage: list[dict] = []
    previous_top: set | None = None
    for day in rebalance_dates():
        table = pd.read_csv(directory / f"ranking-{day}.csv", index_col=0)
        forward = pd.read_csv(directory / f"forward-{day}.csv", index_col=0)
        frame = table.loc[forward.index, ["composite_score"]].join(forward)
        for bound, values in rows.items():
            values.append({"fecha": day, **quarter_stats(apply_bound(frame, bound))})
        top = set(frame.dropna(subset=["retorno"]).nlargest(20, "composite_score").index)
        coverage.append({"fecha": day, "universo": len(table), "con_precio": int(table.precio_fuente.notna().sum()),
                         "elegibles": len(frame), "sin_retorno": int(frame.retorno.isna().sum()),
                         "sin_retorno_desaparece": int((frame.retorno.isna() & frame.termina_antes).sum()),
                         "rotacion_top20": None if previous_top is None else 1 - len(top & previous_top) / 20})
        previous_top = top
    panels = {bound: pd.DataFrame(values) for bound, values in rows.items()}
    result = {"spec_sha256": base["sha256"], "a1_sha256": addendum["sha256"],
              "code_sha256": fs.content_hash(Path(__file__)), "trimestres": len(coverage),
              **analyze_panels(panels), "cobertura": coverage}
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "resultado.json").write_text(json.dumps(fs._json_safe(result), ensure_ascii=False, indent=2) + "\n",
                                           encoding="utf-8")
    return result


if __name__ == "__main__":
    main()
