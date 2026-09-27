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
import hashlib
import json
from datetime import date, timedelta

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


# --- Etapa 4: series aceptadas (comprobación de nivel de precio SEC, #28) ------------------------

def _tiingo_source() -> str:
    from . import historical_tiingo
    return historical_tiingo.source_id("smallmid")


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
    sources = {"yahoo": YAHOO_SOURCE, "wiki": WIKI_SOURCE, "tiingo": _tiingo_source()}
    rows = []
    for number, row in enumerate(tickers.itertuples(index=False), 1):
        symbol = row.ticker_vigente if isinstance(row.ticker_vigente, str) else row.ticker_10k
        if not isinstance(symbol, str):
            continue
        facts = ie.issuer_facts(row.cik)
        for name in ("yahoo", "wiki", "tiingo"):
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
    """(fuente, símbolo) aceptado para ``day`` o None."""
    low = (date.fromisoformat(day) - timedelta(days=400)).isoformat()
    candidates = checks[(checks.cik == cik) & (checks.desde <= low) & (checks.hasta >= day)]
    for name in ("yahoo", "tiingo", "wiki"):
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

    universe = build_universe()
    checks = accepted_series()
    sources = {"yahoo": YAHOO_SOURCE, "wiki": WIKI_SOURCE, "tiingo": _tiingo_source()}
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


if __name__ == "__main__":
    main()
