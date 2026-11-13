"""Synthetic parity and timing of EDGAR fact/metric writes with issuer attribution."""

import ast
import json
import sqlite3
import statistics
import sys
import tempfile
import time
import tracemalloc
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/src"))
ISSUERS, FACTS = 100, 60


def dump(path: Path) -> dict:
    with closing(sqlite3.connect(path)) as db:
        return {t: sorted(db.execute(f"SELECT * FROM {t}").fetchall())
                for t in ("edgar_facts", "entity_observations", "entities")}


def main():
    from gabi import config, edgar, identity

    reference = json.loads((ROOT / "backend/tests/fixtures/edgar_writes_migration.json").read_text(encoding="utf-8"))
    now = datetime(2026, 4, 1, tzinfo=UTC)
    rows = [{"tag": "Revenues", "unit": "USD", "start_date": f"{2000 + i}-01-01", "end_date": f"{2000 + i}-12-31",
             "val": float(i), "form": "10-K", "fp": "FY", "fy": 2000 + i, "filed_date": f"{2001 + i}-02-01",
             "accn": f"a{i}"} for i in range(FACTS)]
    with tempfile.TemporaryDirectory(prefix="gabi-edgar-writes-") as directory:
        paths = {label: Path(directory) / label / "gabi.db" for label in ("anterior", "nuevo")}

        @contextmanager
        def connection():
            config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(config.DB_PATH, timeout=30)) as db:
                db.execute("PRAGMA journal_mode=WAL")
                yield db

        namespace = {"storage": SimpleNamespace(get_connection=connection), "identity": identity}
        for node in ast.parse(reference["edgar"]).body:
            if isinstance(node, ast.FunctionDef) and node.name in {"upsert_edgar_facts", "upsert_edgar_metrics"} or \
                    isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in {"FACTS_SCHEMA", "SCHEMA"}
                                                         for t in node.targets):
                exec(ast.get_source_segment(reference["edgar"], node).replace("    from . import identity\n", ""), namespace)
        namespace["datetime"], namespace["UTC"] = SimpleNamespace(now=lambda tz: now), UTC
        edgar._now = lambda: now

        def run(target):
            def write():
                for i in range(ISSUERS):
                    target["upsert_edgar_facts"](f"S{i}", rows, cik=str(i + 1))
                    target["upsert_edgar_metrics"](f"S{i}", str(i + 1), {"roic": .1})
            return write

        variants = {"anterior": run(namespace), "nuevo": run(vars(edgar))}
        row, outputs = {}, []
        for label, write in variants.items():
            config.DB_PATH = paths[label]
            began = time.perf_counter()
            write()
            cold = time.perf_counter() - began
            outputs.append(dump(paths[label]))
            tracemalloc.start()
            write()
            peak = tracemalloc.get_traced_memory()[1] / 2**20
            tracemalloc.stop()
            warm = []
            for _ in range(3):
                began = time.perf_counter()
                write()
                warm.append(time.perf_counter() - began)
            row[label] = {"cold_s": round(cold, 4), "warm_median_s": round(statistics.median(warm), 4),
                          "peak_python_mib": round(peak, 2)}
        outputs = [{**o, "entities": [e[:3] for e in o["entities"]]} for o in outputs]  # first_seen uses the local day
        assert outputs[0] == outputs[1]
    print(json.dumps({"issuers": ISSUERS, "facts_per_issuer": FACTS, "parity": True, "downloads": 0,
                      "results": {"Hechos y métricas EDGAR": row}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
