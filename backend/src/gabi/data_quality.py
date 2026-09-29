"""Observabilidad de datos: calidad, frescura y procedencia de todo lo que
GABI cachea localmente -- para poder responder no solo qué score produce un
símbolo, sino con qué calidad, frescura y procedencia se calculó.

Cada fuente (precios, fundamentales Yahoo, SEC EDGAR, insider Form 4, FRED
macro, Entity Master) ya llevaba su propio `fetched_at`/`max_age_hours` por
separado, repartido en `storage.py`, `data_fetch.py`, `edgar.py`,
`insider.py`, `macro.py` y `entity_master.py` -- no había un sitio único
donde ver "qué calidad tienen mis datos" (agregado, por universo) ni "de
dónde procede este resultado" (desglosado, por empresa). Este módulo solo
agrega lo que ya existe: no añade ninguna fuente, umbral ni llamada de red
nueva -- todo se lee de la caché local (SQLite/CSV), nunca dispara un
fetch, así que es seguro de usar en tests."""
import hashlib
import json
from datetime import UTC, datetime

import pandas as pd

from . import config, edgar, entity_master, insider, macro, scoring, storage

PRICE_STALE_DAYS = 5  # una acción sin nueva sesión guardada en 5 días naturales va con retraso

# Limitaciones estructurales CONOCIDAS del universo -- no son bugs, son
# techos impuestos por las fuentes gratuitas que usa GABI (ver README,
# "Limitaciones conocidas"). Se muestran SIEMPRE en la UI, sin importar lo
# verdes que salgan los porcentajes en vivo: un 100% de CIK resueltos HOY
# no dice nada sobre la cobertura real de un backtest point-in-time sobre
# 2016-2021, y por eso no basta con un semáforo por umbral -- hace falta
# decirlo explícitamente para no fingir una calidad que no existe.
STRUCTURAL_LIMITATIONS = [
    "SEC EDGAR / CIK histórico: company_tickers.json de la SEC solo mapea registrantes ACTIVOS hoy, "
    "no históricos. En una reconstrucción point-in-time (🕰️ Ranking histórico), la cobertura de "
    "cualquier trimestre anterior a 2022 tiene un techo estructural de ~57-69% -- un % de CIK resueltos "
    "alto en el universo EN VIVO (esta página) no aplica a esos backtests.",
    "Sector point-in-time: no existe una fuente gratuita de sector HISTÓRICO. Entity Master solo "
    "acumula fotos con fecha desde que se implementó -- para la inmensa mayoría de fechas históricas de "
    "hoy, el sector usado en un backtest es una aproximación (el sector ACTUAL), marcada como tal, no "
    "el real de la época.",
]


def _age_hours(fetched_at) -> float | None:
    """`fetched_at`: None, str ISO o datetime -- todas las fuentes de este
    proyecto guardan `datetime.now(UTC).isoformat()`, así que siempre trae
    su propio offset y nunca hace falta (ni sería correcto) asumir una
    zona horaria por nuestra cuenta."""
    if fetched_at is None:
        return None
    if isinstance(fetched_at, str):
        try:
            fetched_at = datetime.fromisoformat(fetched_at)
        except ValueError:
            return None
    if not isinstance(fetched_at, datetime) or fetched_at.tzinfo is None:
        return None
    age = (datetime.now(UTC) - fetched_at).total_seconds() / 3600
    return age if age >= 0 else None


def local_cik_status(symbols: list) -> dict:
    """Resuelve únicamente contra archivos/tablas locales, sin refrescar ni escribir."""
    result = dict.fromkeys(symbols)
    with storage.get_connection() as conn:
        exists = conn.execute("SELECT 1 FROM sqlite_master WHERE name='cik_resolutions'").fetchone()
        if exists:
            for symbol, cik in conn.execute("SELECT symbol, cik FROM cik_resolutions"):
                if symbol in result:
                    result[symbol] = cik
    if edgar.CIK_CACHE.exists():
        frame = pd.read_csv(edgar.CIK_CACHE, dtype={"cik": str})
        mapping = dict(zip(frame["symbol"], frame["cik"], strict=True))
        for symbol in symbols:
            result[symbol] = mapping.get(symbol, mapping.get(symbol.replace(".", "-"), result[symbol]))
    return result


def _fetched_at_summary(label: str, symbols: list, fetched_map: dict, threshold_hours: float) -> dict:
    n = len(symbols)
    raw_ages = [_age_hours(fetched_map.get(s)) for s in symbols]
    ages: list[float] = [a for a in raw_ages if a is not None]
    have = len(ages)
    fresh = sum(1 for a in ages if a <= threshold_hours)
    return {
        "label": label,
        "coverage": have / n if n else 0.0,
        "fresh": fresh / n if n else 0.0,
        "threshold_hours": threshold_hours,
        "oldest_hours": max(ages) if ages else None,
        "have": have, "fresh_n": fresh, "total": n,
    }


def universe_summary(symbols: list) -> dict:
    """Cobertura y frescura agregadas de todo el universo dado, fuente por
    fuente -- el "qué calidad tienen mis datos" de un vistazo. No dispara
    ningún fetch: si algo no está en caché, cuenta como cobertura 0, no
    como error."""
    n = len(symbols)
    if n == 0:
        return {"n_symbols": 0, "sources": {}, "cik": None, "macro": None}

    price_coverage = storage.get_price_coverage(symbols)
    has_price = 0
    fresh_price = 0
    oldest_price_date = None
    today = pd.Timestamp.now(tz="UTC").normalize()
    for s in symbols:
        row = price_coverage.get(s, {})
        if not row.get("adjusted_count"):
            continue
        has_price += 1
        latest = row.get("latest_adjusted_date")
        if not latest:
            continue
        age_days = (today - pd.Timestamp(latest, tz="UTC")).days
        if 0 <= age_days <= PRICE_STALE_DAYS:
            fresh_price += 1
        if oldest_price_date is None or latest < oldest_price_date:
            oldest_price_date = latest

    sources = {
        "prices": {
            "label": "Precios (Yahoo)", "coverage": has_price / n, "fresh": fresh_price / n,
            "threshold_hours": PRICE_STALE_DAYS * 24, "oldest_hours": None, "oldest_date": oldest_price_date,
            "have": has_price, "fresh_n": fresh_price, "total": n,
        },
        "fundamentals": _fetched_at_summary(
            "Fundamentales (Yahoo)", symbols, storage.get_fundamentals_fetched_at(symbols),
            config.CACHE_MAX_AGE_HOURS),
        "edgar": _fetched_at_summary(
            "SEC EDGAR", symbols, edgar.get_edgar_fetched_at(symbols), config.EDGAR_CACHE_MAX_AGE_HOURS),
        "insider": _fetched_at_summary(
            "Insider (Form 4)", symbols, insider.get_insider_fetched_at(symbols), 24),
    }
    edgar_with_facts = edgar.get_symbols_with_facts(symbols)
    sources["edgar"]["with_facts_pct"] = len(edgar_with_facts & set(symbols)) / n

    today_iso = pd.Timestamp.now(tz="UTC").date().isoformat()
    entity_snapshots_today = entity_master.get_sector_asof(symbols, today_iso)
    has_snapshot = sum(1 for s in symbols if entity_snapshots_today[s]["sector"])
    # "is_approximate" no dice nada preguntando por HOY -- cualquier foto que
    # exista ya es <= hoy por construcción, así que siempre saldría exacta.
    # Lo que de verdad importa es cuánto ALCANCE point-in-time real hay hacia
    # atrás: se pregunta por una fecha de referencia pasada (1 año) como
    # proxy del tipo de fecha que usa un backtest -- si la única foto
    # disponible es de hace unos días, para esa fecha sigue siendo
    # aproximación, y eso es precisamente la limitación estructural
    # documentada en STRUCTURAL_LIMITATIONS.
    reference_past_date = (pd.Timestamp.now(tz="UTC") - pd.DateOffset(years=1)).date().isoformat()
    entity_snapshots_past = entity_master.get_sector_asof(symbols, reference_past_date)
    exact_for_reference_past = sum(
        1 for s in symbols
        if entity_snapshots_past[s]["sector"] and not entity_snapshots_past[s]["is_approximate"]
    )
    sources["entity_master"] = {
        "label": "Entity Master (sector)", "coverage": has_snapshot / n,
        "fresh": exact_for_reference_past / n,  # "fresco" = point-in-time real hace 1 año, no aproximado
        "threshold_hours": None, "oldest_hours": None,
        "have": has_snapshot, "fresh_n": exact_for_reference_past, "total": n,
    }

    cik_status = None
    local_ciks = local_cik_status(symbols)
    if edgar.CIK_CACHE.exists() or any(local_ciks.values()):
        resolved = sum(bool(cik) for cik in local_ciks.values())
        cik_status = {"resolved": resolved, "total": n, "pct": resolved / n}

    macro_fetched = macro.get_all_fetched_at()
    fred_dates = {}
    for series_id in macro.SERIES:
        history = macro.get_series_history(series_id)
        valid = history.dropna(subset=["value"]) if not history.empty else history
        fred_dates[series_id] = str(valid.index.max().date()) if not valid.empty else None
    fred = _fetched_at_summary("FRED", list(macro.SERIES), macro_fetched, 24)
    fred["have"] = sum(value is not None for value in fred_dates.values())
    fred["coverage"] = fred["have"] / len(macro.SERIES)
    fred["latest_dates"] = fred_dates
    fred["fresh_n"] = sum(
        fred_dates[s] is not None and (age := _age_hours(macro_fetched.get(s))) is not None and age <= 24
        for s in macro.SERIES
    )
    fred["fresh"] = fred["fresh_n"] / len(macro.SERIES)
    sources["fred"] = fred
    macro_status = None
    if macro_fetched:
        ages: list[float] = [a for dt in macro_fetched.values() if (a := _age_hours(dt)) is not None]
        macro_status = {
            "n_series": len(macro_fetched),
            "oldest_hours": max(ages) if ages else None,
            "threshold_hours": 24,
        }

    return {"n_symbols": n, "sources": sources, "cik": cik_status, "macro": macro_status,
            "status": "degraded", "structural_limitations": list(STRUCTURAL_LIMITATIONS)}


def symbol_provenance(symbol: str, as_of: str | None = None) -> dict:
    """Para una empresa concreta: qué fuente y qué fecha respalda cada pieza
    de dato detrás de su score actual -- el "de dónde procede este
    resultado". Distingue `fetched_at` (cuándo lo descargó GABI) de la fecha
    real del propio informe (`latest_10k_date`/`latest_10q_date`) -- una
    descarga de ayer puede seguir respaldada por un 10-K de hace más de un
    año, si la empresa no ha presentado nada nuevo desde entonces."""
    price_row = storage.get_price_coverage([symbol]).get(symbol, {})
    price_age_hours = None
    latest_price_date = price_row.get("latest_adjusted_date")
    if latest_price_date:
        today = pd.Timestamp.now(tz="UTC").normalize()
        price_age_hours = (today - pd.Timestamp(latest_price_date, tz="UTC")).days * 24
    fundamentals = storage.get_fundamentals([symbol]).get(symbol)
    fundamentals_fetched_at = fundamentals["fetched_at"] if fundamentals else None
    edgar_fetched_at = edgar.get_edgar_fetched_at([symbol]).get(symbol)
    edgar_metrics = edgar.get_edgar_metrics([symbol]).get(symbol, {})
    edgar_has_facts = symbol in edgar.get_symbols_with_facts([symbol])
    insider_fetched_at = insider.get_insider_fetched_at([symbol]).get(symbol)
    # is_approximate contra HOY siempre saldría False si existe cualquier
    # foto (toda foto ya existente es <= hoy por construcción) -- se
    # pregunta contra una fecha de referencia pasada (1 año), igual que en
    # universe_summary, para que el flag diga algo real sobre el alcance
    # point-in-time disponible, no un "sí" trivial.
    reference_past_date = (pd.Timestamp.now(tz="UTC") - pd.DateOffset(years=1)).date().isoformat()
    reference_past_date = as_of or reference_past_date
    entity_snapshot = entity_master.get_sector_asof([symbol], reference_past_date)[symbol]

    return {
        "symbol": symbol,
        "cik": local_cik_status([symbol])[symbol],
        "prices": {
            "latest_date": latest_price_date,
            "adjusted_sessions": price_row.get("adjusted_count", 0),
            "age_hours": price_age_hours,
            "threshold_hours": PRICE_STALE_DAYS * 24,
        },
        "fundamentals": {
            "fetched_at": fundamentals_fetched_at,
            "age_hours": _age_hours(fundamentals_fetched_at),
            "threshold_hours": config.CACHE_MAX_AGE_HOURS,
        },
        "edgar": {
            "fetched_at": edgar_fetched_at,
            "age_hours": _age_hours(edgar_fetched_at),
            "threshold_hours": config.EDGAR_CACHE_MAX_AGE_HOURS,
            "has_facts": edgar_has_facts,
            "latest_10k_date": edgar_metrics.get("latest_10k_date"),
            "latest_10q_date": edgar_metrics.get("latest_10q_date"),
        },
        "insider": {
            "fetched_at": insider_fetched_at,
            "age_hours": _age_hours(insider_fetched_at),
            "threshold_hours": 24,
        },
        "entity_master": {
            "reference_date": reference_past_date,
            "status": ("missing" if not entity_snapshot["sector"] else
                       "approximate" if entity_snapshot["is_approximate"] else "point_in_time"),
            "sector": entity_snapshot["sector"],
            "effective_date": entity_snapshot["effective_date"],
            "is_approximate": entity_snapshot["is_approximate"],
            "has_snapshot": entity_snapshot["effective_date"] is not None,
        },
    }


def score_block_coverage(df: pd.DataFrame) -> dict:
    """Para cada bloque del score (Value/Quality/Momentum/Risk): qué
    fracción del universo dado tiene TODAS sus métricas oficiales
    disponibles (`scoring.SCORE_METRICS`), qué fracción tiene AL MENOS una,
    y qué fracción no tiene ninguna -- el "qué % del S&P 500 tiene datos
    completos para cada bloque del score" de un vistazo.

    `df` debe venir ya de `scoring.build_scores` (necesita las columnas
    `<métrica>_pct`) -- esta función es agregación pura sobre lo que ya
    exista, no calcula nada ni toca red."""
    n = len(df)
    result = {}
    for block, cols in scoring.SCORE_METRICS.items():
        pct_cols = [f"{c}_pct" for c in cols]
        available = [c for c in pct_cols if c in df.columns]
        if n == 0 or not available:
            result[block] = {"complete": 0.0, "any": 0.0, "none": 1.0 if n else 0.0, "n_metrics": len(cols)}
            continue
        counts = df[available].notna().sum(axis=1)
        result[block] = {
            "complete": float((counts == len(cols)).sum()) / n,
            "any": float((counts > 0).sum()) / n,
            "none": float((counts == 0).sum()) / n,
            "n_metrics": len(cols),
        }
    return result


def recent_errors_summary(since_hours: float = 24 * 7) -> pd.DataFrame:
    """Fallos de actualización de los últimos `since_hours` (por defecto, 7
    días) de cualquier fuente -- ver `storage.record_update_errors`."""
    return storage.get_recent_update_errors(since_hours=since_hours)


def compute_data_fingerprint(symbols: list | None = None, *, inputs: dict | None = None) -> str:
    """SHA-256 v2 del contenido local, en una transacción de lectura coherente.

    Incluye precios (también benchmark), splits, XBRL, fundamentales, sectores,
    CIK, FRED y composición del universo. None incluye todos los símbolos.
    El llamador debe capturarlo al ejecutar, y conservarlo con el resultado.
    Identifica una caché: no conserva por sí solo una copia recuperable de ella.
    """
    selected = None if symbols is None else sorted(set(symbols) | {config.BENCHMARK_SYMBOL})
    digest = hashlib.sha256()

    def feed(value):
        digest.update(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                 separators=(",", ":"), default=str).encode("utf-8"))
        digest.update(b"\n")

    feed({"version": 2, "symbols": selected, "inputs": inputs or {}})
    tables = ("prices", "splits", "fundamentals", "edgar_metrics", "edgar_facts",
              "entity_snapshots", "cik_resolutions", "macro_series", "macro_meta",
              "entities", "entity_aliases", "entity_observations", "entity_candidates")
    with storage.get_connection() as conn:
        conn.execute("BEGIN")
        existing = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table in tables:
            feed(table)
            if table not in existing:
                continue
            columns = [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')]
            # Download times do not change the actual financial input.
            columns = [c for c in columns if c not in {"fetched_at", "resolved_at"}]
            feed(columns)
            fields = ",".join(f'"{c}"' for c in columns)
            query = f'SELECT {fields} FROM "{table}"'
            params = []
            if selected is not None and "symbol" in columns and not table.startswith("entit"):
                query += " WHERE symbol IN (" + ",".join("?" for _ in selected) + ")"
                params = selected
            query += " ORDER BY " + fields
            for row in conn.execute(query, params):
                feed([json.loads(value) if column.endswith("_json") and value else value
                      for column, value in zip(columns, row, strict=True)])
    for name in ("sp500_constituents.csv", "sp500_historical_membership.csv", "sec_cik_map.csv"):
        path = config.DATA_DIR / name
        feed(name)
        if path.exists():
            frame = pd.read_csv(path, dtype=str).fillna("")
            columns = sorted(frame.columns)
            feed(columns)
            for row in sorted(frame[columns].itertuples(index=False, name=None)):
                feed(row)
    return "v2:" + digest.hexdigest()


# Umbrales por defecto para los avisos visibles en Screener/Ranking
# histórico/Decisiones -- configurables (se pasan como argumento), estos
# valores son solo el punto de partida razonable.
DEFAULT_DEGRADED_BLOCK_THRESHOLD = 0.70  # % de cobertura COMPLETA de un bloque por debajo del cual se avisa
DEFAULT_CONFIDENCE_THRESHOLD = 60.0  # confidence (0-100) de una candidata por debajo del cual se avisa


def ranking_quality(df: pd.DataFrame) -> dict:
    """Diagnóstico serializable del universo realmente evaluado en una fecha."""
    missing = df.get("sector", pd.Series(index=df.index, dtype=object)).isna()
    approximate = df.get("sector_is_approximate", pd.Series(True, index=df.index)).fillna(True)
    return {
        "blocks": score_block_coverage(df),
        "sector_degraded": float((missing | approximate).mean()) if len(df) else 1.0,
        "identity_unresolved": float(df["identity_status"].ne("resolved").mean()) if "identity_status" in df else None,
    }


def ranking_quality_warnings(quality: dict, threshold: float = DEFAULT_DEGRADED_BLOCK_THRESHOLD) -> list[str]:
    warnings = block_coverage_warnings(quality["blocks"], threshold)
    unresolved = quality.get("identity_unresolved")
    if unresolved is not None and unresolved > 0:
        warnings.append(f"Identidad histórica sin acreditar en {unresolved:.0%} del universo; excluida del score.")
    if quality["sector_degraded"] > 1 - threshold:
        warnings.append(f"Sector aproximado o ausente en {quality['sector_degraded']:.0%} del universo.")
    return warnings


def block_coverage_warnings(block_coverage: dict, threshold: float = DEFAULT_DEGRADED_BLOCK_THRESHOLD) -> list[str]:
    """Mensajes para los bloques del score cuya cobertura COMPLETA cae por
    debajo de `threshold` -- pensado para mostrarse como aviso visible junto
    a un ranking o backtest, no solo en esta página de diagnóstico."""
    warnings = []
    for block, info in block_coverage.items():
        if info["complete"] < threshold:
            warnings.append(
                f"**{block.capitalize()}**: solo {info['complete']:.0%} del universo tiene TODAS las "
                f"métricas de este bloque (umbral configurado: {threshold:.0%})."
            )
    return warnings


def low_confidence_candidates(
    df: pd.DataFrame, symbols, threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> list[dict]:
    """De `symbols` (deben estar en el índice de `df`, que debe traer
    `confidence`/`score_coverage` de `scoring.build_scores` +
    `scoring.compute_confidence`): cuáles tienen `confidence` por debajo de
    `threshold` -- para avisar cuando un resultado CONCRETO (un plan de
    cartera, un ranking) se apoya en candidatas con poco dato detrás, no
    solo para el diagnóstico agregado de `universe_summary`."""
    if "confidence" not in df.columns:
        return []
    out = []
    for s in symbols:
        if s not in df.index:
            continue
        conf = df.loc[s, "confidence"]
        if pd.notna(conf) and conf < threshold:
            coverage = df.loc[s, "score_coverage"] if "score_coverage" in df.columns else None
            coverage_value = float(coverage) if coverage is not None and pd.notna(coverage) else None
            out.append({"symbol": s, "confidence": float(conf), "score_coverage": coverage_value})
    return out
