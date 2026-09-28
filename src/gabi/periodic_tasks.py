"""Tareas periódicas que protegen la evidencia prospectiva de GABI (issue #46).

    python -m gabi.periodic_tasks --status   # qué vence; no modifica nada
    python -m gabi.periodic_tasks --run      # refresca datos y registra rebalanceos vencidos
    python -m gabi.periodic_tasks --tiingo   # reanuda la cola de Tiingo del #44 (lenta)

Un rebalanceo de una prueba ciega solo se registra si ha llegado su fecha y
los precios son del último día de mercado cerrado: registrar con precios
viejos metería en el primer trimestre información ya conocida.
"""

import argparse
import json
from datetime import UTC, date, datetime
from pathlib import Path

from . import blind_validation, config, storage
from . import factor_stability as fs

BENCHMARKS = ["SPY", "RSP"]  # RSP: S&P 500 equiponderado, benchmark secundario de #42 y #43
SOON_DAYS = 7
MAX_STALE_SHARE = 0.05  # como mucho un 5 % del universo con el último precio anterior a la última sesión


# Rutas calculadas en cada llamada para respetar config.DATA_DIR (los tests lo aíslan).
def log_path() -> Path:
    return config.DATA_DIR / "periodic_tasks" / "log.jsonl"


def tiingo_queue_path() -> Path:
    return config.DATA_DIR / "smallmid_test" / "tiingo_symbols.txt"


def tiingo_lock_path() -> Path:
    return config.DATA_DIR / "periodic_tasks" / "tiingo.lock"


def last_session(now: datetime | None = None) -> str:
    from .history_refresh import last_completed_session
    return last_completed_session(now or datetime.now(UTC))


def latest_price(symbol: str) -> str | None:
    with storage.get_connection() as conn:
        row = conn.execute("SELECT MAX(date) FROM prices WHERE symbol=? AND adj_close IS NOT NULL", (symbol,)).fetchone()
    return row[0] if row else None


def live_symbols() -> list[str]:
    """Universo vigente según la caché (sin red); los que ya salieron del índice no cuentan."""
    from . import screener
    return screener.get_universe()["symbol"].tolist()


def stale_share(now: datetime | None = None) -> float:
    """Fracción del universo vigente cuyo último precio es anterior a la última sesión (o no tiene)."""
    session = last_session(now)
    symbols = live_symbols()
    return sum((latest_price(s) or "") < session for s in symbols) / len(symbols) if symbols else 1.0


def prices_fresh(now: datetime | None = None) -> bool:
    """SPY y RSP al día y como mucho un 5 % del universo reciente sin el último cierre."""
    session = last_session(now)
    return all(latest_price(s) == session for s in BENCHMARKS) and stale_share(now) <= MAX_STALE_SHARE


def blind_status(today: date | None = None) -> list[dict]:
    today = today or date.today()
    rows = []
    for row in blind_validation.list_validations().itertuples():
        status = blind_validation.get_status(int(row.id))
        due = status["next_rebalance_due"]
        rows.append({"id": int(row.id), "nombre": row.name, "estado": row.status, "proximo": due,
                     "vencido": bool(due and row.status == "locked" and today.isoformat() >= due),
                     "dias": (date.fromisoformat(due) - today).days if due else None,
                     "integridad": status["integrity"]["ok"], "periodos": status["n_periods"]})
    return rows


def due_soon(days: int = SOON_DAYS, today: date | None = None) -> list[dict]:
    """Pruebas ciegas bloqueadas con un rebalanceo en ``days`` días o vencido (aviso de la app)."""
    return [row for row in blind_status(today) if row["estado"] == "locked" and row["dias"] is not None
            and row["dias"] <= days]


def tiingo_queue() -> dict:
    from . import historical_tiingo
    if not tiingo_queue_path().exists():
        return {"cola": 0, "descargados": 0, "en_curso": False}
    queue = [symbol.upper() for symbol in tiingo_queue_path().read_text().split()]
    directory = historical_tiingo._window("smallmid")[3]
    done = {p.stem for p in directory.glob("*.json")} if directory.exists() else set()
    return {"cola": len(queue), "descargados": sum(symbol in done for symbol in queue),
            "en_curso": tiingo_lock_path().exists()}


def status(now: datetime | None = None) -> dict:
    return {"fecha": (now or datetime.now(UTC)).date().isoformat(), "ultima_sesion": last_session(now),
            "precios": {s: latest_price(s) for s in BENCHMARKS}, "universo_sin_ultimo_cierre": stale_share(now),
            "precios_al_dia": prices_fresh(now),
            "pruebas_ciegas": blind_status((now or datetime.now(UTC)).date()), "tiingo_44": tiingo_queue()}


def _log(event: dict) -> None:
    path = log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(fs._json_safe({"at": datetime.now(UTC).isoformat(), **event}), ensure_ascii=False) + "\n")


def refresh_data() -> dict:
    """Universo vivo y sus datos (precios, fundamentales, SEC) más los benchmarks."""
    from . import screener
    universe = screener.get_universe(force_refresh=True)
    symbols = [*universe["symbol"].tolist(), *BENCHMARKS]
    result = screener.refresh_data(symbols)
    return {"simbolos": len(symbols), "fallos": len(result.get("failed", {}))}


def record_due(now: datetime | None = None) -> list[dict]:
    """Registra los rebalanceos vencidos, solo con precios del último día de mercado."""
    outcomes = []
    fresh = prices_fresh(now)
    for row in blind_status((now or datetime.now(UTC)).date()):
        if not row["vencido"]:
            continue
        if not fresh:
            outcomes.append({"id": row["id"], "registrado": False,
                             "motivo": f"precios no actualizados (SPY {latest_price('SPY')}, "
                                       f"RSP {latest_price('RSP')}, sin último cierre "
                                       f"{stale_share(now):.1%}, última sesión {last_session(now)})"})
            continue
        if not row["integridad"]:
            outcomes.append({"id": row["id"], "registrado": False, "motivo": "cadena de hashes rota; revisar"})
            continue
        result = blind_validation.record_rebalance(row["id"])
        outcomes.append({"id": row["id"], "registrado": True, "fecha": result["rebalance_date"],
                         "hash": result["record_hash"], "posiciones": len(result["symbols"])})
    return outcomes


def run(*, refresh: bool = True) -> dict:
    report: dict = {"antes": status()}
    if refresh:
        report["refresco"] = refresh_data()
    report["rebalanceos"] = record_due()
    report["despues"] = status()
    _log({"accion": "run", **report})
    return report


def resume_tiingo() -> dict:
    from . import historical_tiingo, smallmid_test
    lock = tiingo_lock_path()
    if lock.exists():
        return {"omitido": f"ya hay una descarga en curso (borrar {lock} si no es así)"}
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(datetime.now(UTC).isoformat())
    try:
        queue = [symbol.upper() for symbol in tiingo_queue_path().read_text().split()]
        fetched = historical_tiingo.fetch(queue, window="smallmid")
        imported = historical_tiingo.import_cached("smallmid")
        smallmid_test.mark_tiingo_complete(fetched)  # A3: cola recorrida sin tope -> datos congelados
    finally:
        lock.unlink(missing_ok=True)
    report = {"descarga": fetched, "importacion": imported, "cola": tiingo_queue()}
    _log({"accion": "tiingo", **report})
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--no-refresh", action="store_true", help="Con --run: no refrescar datos antes")
    parser.add_argument("--tiingo", action="store_true")
    args = parser.parse_args()
    if args.run:
        print(json.dumps(fs._json_safe(run(refresh=not args.no_refresh)), ensure_ascii=False, indent=2))
    elif args.tiingo:
        print(json.dumps(fs._json_safe(resume_tiingo()), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(fs._json_safe(status()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
