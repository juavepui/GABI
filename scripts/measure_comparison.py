"""Measure Comparar (#194) with 5 companies on synthetic temporary data, never data/gabi.db."""
import argparse
import json
import platform
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory, gettempdir
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/tests"))
from fastapi.testclient import TestClient  # noqa: E402
from market_fixture import TODAY, seed_fixture  # noqa: E402
from test_checklist import _excel_example, _frame  # noqa: E402

from gabi.infrastructure.settings import Settings  # noqa: E402
from gabi.infrastructure.storage.sec_xbrl import FACTS_SCHEMA  # noqa: E402
from gabi_api.bootstrap import create_app  # noqa: E402

COMPARED = ["T000", "T001", "T002", "T003", "T004"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--companies", type=int, default=80, help="sector peers with SEC facts (one sector)")
    parser.add_argument("--sessions", type=int, default=1250)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    with TemporaryDirectory(prefix="gabi-comparison-measure-") as temporary:
        root = Path(temporary).resolve()
        assert root.is_relative_to(Path(gettempdir()).resolve())
        seed_fixture(root, args.companies, args.sessions)
        frame = _frame(_excel_example())
        with closing(sqlite3.connect(root / "gabi.db")) as db:
            db.executescript(FACTS_SCHEMA)
            db.executemany("INSERT INTO edgar_facts VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                           [(f"T{i:03}", r.tag, r.unit, r.start_date, r.end_date, r.val, r.form, r.fp, r.fy,
                             r.filed_date, r.accn) for i in range(args.companies) for r in frame.itertuples()])
            db.commit()
        query = "&".join("symbols=" + symbol for symbol in COMPARED)
        report: dict = {"python": platform.python_version(), "platform": platform.system(),
                        "sector_peers_with_sec_facts": args.companies, "sessions": args.sessions,
                        "compared": COMPARED, "seconds": {}}
        with TestClient(create_app(Settings(root), today=lambda: TODAY)) as client:
            client.get("/api/v1/ranking?limit=1")  # the ranking is shared by every page; warm it first
            for name, path in (("metrics", "/api/v1/comparison?" + query),
                               ("checklist", "/api/v1/comparison/checklist?" + query),
                               ("prices_252", "/api/v1/comparison/prices?bars=252&" + query),
                               ("prices_756", "/api/v1/comparison/prices?bars=756&" + query)):
                runs = []
                for _ in range(args.repeats):
                    started = perf_counter()
                    response = client.get(path)
                    runs.append(round(perf_counter() - started, 4))
                    assert response.status_code == 200, response.text
                report["seconds"][name] = {"cold": runs[0], "warm": min(runs[1:]) if runs[1:] else None}
        text = json.dumps(report, indent=2)
        print(text)
        if args.output:
            args.output.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
