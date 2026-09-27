"""Viabilidad de probar GABI fuera del S&P 500 con datos gratuitos (issue #44).

Regla de universo, fijada antes de mirar resultados: en cada fecha D (30 de
junio de 2012, 2017 y 2022), las empresas con un *public float* SEC
(``dei:EntityPublicFloat``, frames XBRL) fechado en los 15 meses anteriores
y comprendido entre 300 millones y 20.000 millones de USD, excluidos los
emisores del S&P 500 en D. No es una muestra de ningún índice de pago: sale
solo de datos SEC, así que incluye a las empresas que después desaparecen.

El estudio mide si esas empresas tendrían identidad, fundamentales y, sobre
todo, precios con datos gratuitos, en particular las que dejan de presentar
informes en los 18 meses siguientes (las que un universo con sesgo de
supervivencia perdería).
"""

import argparse
import json
import random
import zipfile
from datetime import date, timedelta

import pandas as pd

from . import config, historical_membership, historical_period, identity, storage
from . import factor_stability as fs
from . import historical_issuer_evidence as ie

OUTPUT = config.BASE_DIR / "docs" / "smallmid-feasibility"
DATES = ("2012-06-30", "2017-06-30", "2022-06-30")
FLOAT_MIN, FLOAT_MAX = 3e8, 2e10
LOOKBACK_DAYS = 455  # 15 meses
SURVIVAL_DAYS = 548  # 18 meses
SAMPLE_PER_DATE = 60
SEED = 44


def _sp500_ciks(day: str) -> set[str]:
    """CIK de los miembros del S&P 500 en ``day`` según la identidad acreditada (#27, #34)."""
    period = historical_period.for_date(day)
    if period is None:
        raise ValueError(f"{day} fuera de los periodos acreditados")
    data = historical_membership.constituents_as_of(day, source_id=historical_period.REFERENCE_SOURCE_FULL,
                                                    compare_reference=False, identity_source=period.identity_source)
    return {identity.normalize_cik(m["cik"]) for m in data["members"] if m.get("cik")}


def universe(day: str) -> pd.DataFrame:
    """Empresas elegibles en ``day`` con su float y si siguen presentando informes 18 meses después."""
    frames = ie.load_frames()
    target = date.fromisoformat(day)
    low = (target - timedelta(days=LOOKBACK_DAYS)).isoformat()
    later = (target + timedelta(days=SURVIVAL_DAYS)).isoformat()
    excluded = _sp500_ciks(day)
    rows = []
    for cik, kinds in frames.items():
        floats = [r for r in kinds.get("public_float", []) if r["val"] and low <= r["end"] <= day]
        if not floats or cik in excluded:
            continue
        latest = max(floats, key=lambda r: r["end"])
        if not FLOAT_MIN <= float(latest["val"]) <= FLOAT_MAX:
            continue
        future = [r for r in kinds.get("public_float", []) + kinds.get("cover_shares", [])
                  if day < r["end"] <= later]
        rows.append({"cik": cik, "public_float": float(latest["val"]), "float_date": latest["end"],
                     "sigue_presentando_18m": bool(future)})
    return pd.DataFrame(rows)


def _tiingo_listings() -> pd.DataFrame:
    from . import historical_tiingo as tiingo
    frame = pd.read_csv(zipfile.ZipFile(tiingo.DIRECTORY / "supported_tickers.zip").open("supported_tickers.csv"))
    frame = frame[(frame.assetType == "Stock") & (frame.priceCurrency == "USD")].dropna(subset=["ticker"])
    frame["ticker"] = frame.ticker.str.upper()
    return frame


def sample_coverage(day: str, frame: pd.DataFrame) -> list[dict]:
    """Muestra estratificada (supervivientes y desaparecidas): nombre, ticker y precio gratuito disponible."""
    rng = random.Random(f"{SEED}-{day}")
    gone = frame[~frame.sigue_presentando_18m].cik.tolist()
    alive = frame[frame.sigue_presentando_18m].cik.tolist()
    chosen = [(c, False) for c in rng.sample(gone, min(len(gone), SAMPLE_PER_DATE // 2))] + \
             [(c, True) for c in rng.sample(alive, min(len(alive), SAMPLE_PER_DATE // 2))]
    ie.fetch_submissions({c for c, _ in chosen})
    listings = _tiingo_listings()
    needed_from = (date.fromisoformat(day) - timedelta(days=370)).isoformat()
    needed_to = (date.fromisoformat(day) + timedelta(days=92)).isoformat()
    rows = []
    for cik, alive_flag in chosen:
        life = ie.listing_life(cik)
        tickers = [identity.normalize_symbol(t) for t in (life or {}).get("current_tickers", []) if t]
        annual = [r for r in (life or {}).get("annual_reports", []) if r["filed"] <= day]
        tiingo = listings[listings.ticker.isin(tickers)]
        covers = tiingo[(tiingo.startDate <= needed_from) & (tiingo.endDate.astype(str) >= needed_to)]
        # Rescate del ticker histórico: símbolo declarado en el último 10-K previo a la fecha (#34).
        recovered = None
        if not tickers and annual:
            try:
                _url, path = ie.fetch_annual_report(cik, annual[-1])
                found = ie.annual_report_symbols(path.read_text(encoding="utf-8", errors="ignore"), extended=True)
                recovered = next(iter(found)) if len(found) == 1 else None
            except Exception:  # documento no disponible: cuenta como no recuperado
                recovered = None
        old_listing = listings[listings.ticker == recovered] if recovered else listings.iloc[0:0]
        old_covers = old_listing[(old_listing.startDate <= needed_from) & (old_listing.endDate.astype(str) >= needed_to)]
        rows.append({"ticker_recuperado_10k": recovered,
                     "tiingo_ticker_recuperado_cubre_ventana": bool(len(old_covers)),
                     "fecha": day, "cik": cik, "sigue_presentando_18m": alive_flag,
                     "nombre": (life or {}).get("name"), "tickers_sec_actuales": ",".join(tickers),
                     "ticker_sec_actual": bool(tickers), "10k_previo": bool(annual),
                     "tiingo_ticker_actual_cubre_ventana": bool(len(covers))})
    return rows


def run(*, sample: bool = False) -> dict:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report: dict = {"regla": {"float_min": FLOAT_MIN, "float_max": FLOAT_MAX, "lookback_dias": LOOKBACK_DAYS,
                              "supervivencia_dias": SURVIVAL_DAYS, "excluye": "emisores del S&P 500 en la fecha"},
                    "fechas": {}}
    samples = []
    for day in DATES:
        frame = universe(day)
        frame.to_csv(OUTPUT / f"universo-{day}.csv", index=False)
        report["fechas"][day] = {"empresas": len(frame),
                                 "desaparecen_en_18m": int((~frame.sigue_presentando_18m).sum()),
                                 "pct_desaparecen": float((~frame.sigue_presentando_18m).mean()),
                                 "float_mediano_musd": float(frame.public_float.median() / 1e6)}
        print(day, report["fechas"][day], flush=True)
        if sample:
            samples += sample_coverage(day, frame)
    if sample:
        table = pd.DataFrame(samples)
        table.to_csv(OUTPUT / "muestra-cobertura.csv", index=False)
        report["muestra"] = {
            f"{day}_{'supervivientes' if alive else 'desaparecidas'}": {
                "n": len(g), "ticker_sec_actual": float(g.ticker_sec_actual.mean()),
                "tiingo_cubre_ventana": float(g.tiingo_ticker_actual_cubre_ventana.mean()),
                "ticker_recuperado_10k": float(g.ticker_recuperado_10k.notna().mean()),
                "tiingo_cubre_con_ticker_recuperado": float(g.tiingo_ticker_recuperado_cubre_ventana.mean()),
                "algun_precio_gratuito": float((g.tiingo_ticker_actual_cubre_ventana
                                                | g.tiingo_ticker_recuperado_cubre_ventana).mean())}
            for (day, alive), g in table.groupby(["fecha", "sigue_presentando_18m"])}
    with storage.get_connection() as conn:
        report["frames_ultimo_ano"] = max(int(r[0][:4]) for r in conn.execute("SELECT '2025'"))
    (OUTPUT / "viabilidad.json").write_text(json.dumps(fs._json_safe(report), ensure_ascii=False, indent=2) + "\n",
                                            encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", action="store_true", help="Además, muestra con descarga de submissions SEC")
    args = parser.parse_args()
    print(json.dumps(fs._json_safe(run(sample=args.sample)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
