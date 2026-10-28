"""Measure the Ranking with every column (#196) on synthetic temporary data, never data/gabi.db."""
import argparse
import json
import platform
import sys
from pathlib import Path
from tempfile import TemporaryDirectory, gettempdir
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/tests"))
from fastapi.testclient import TestClient  # noqa: E402
from market_fixture import TODAY, seed_fixture  # noqa: E402

from gabi.infrastructure.settings import Settings  # noqa: E402
from gabi_api.bootstrap import create_app  # noqa: E402

# Every column the Ranking can show, as the CSV names them.
ALL_COLUMNS = ["price", "composite_score", "confidence", "market_cap", "pe", "value_score", "quality_score",
               "momentum_score", "risk_score", "roe", "debt_to_equity", "dividend_yield", "momentum_12m", "volatility",
               "next_earnings_date", "next_earnings_days"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--companies", type=int, default=500)
    parser.add_argument("--sessions", type=int, default=1250)
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()
    with TemporaryDirectory(prefix="gabi-ranking-measure-") as temporary:
        root = Path(temporary).resolve()
        assert root.is_relative_to(Path(gettempdir()).resolve())
        seed_fixture(root, args.companies, args.sessions)
        columns = "&".join("columns=" + column for column in ALL_COLUMNS)
        paths = {
            "ranking_page_100": "/api/v1/ranking?limit=100",
            "ranking_page_100_sorted_volatility": "/api/v1/ranking?limit=100&order_by=volatility",
            "ranking_filtered": "/api/v1/ranking?limit=100&exclude_sectors=Financials&earnings=exclude",
            "csv_all_rows_all_columns": "/api/v1/ranking/export.csv?" + columns,
        }
        report: dict = {"python": platform.python_version(), "platform": platform.system(),
                        "companies": args.companies + 4, "sessions": args.sessions, "seconds": {}, "bytes": {}}
        with TestClient(create_app(Settings(root), today=lambda: TODAY)) as client:
            started = perf_counter()
            client.get("/api/v1/ranking?limit=1")
            report["seconds"]["cold_ranking_cache"] = round(perf_counter() - started, 4)
            for name, path in paths.items():
                runs = []
                for _ in range(args.repeats):
                    started = perf_counter()
                    response = client.get(path)
                    runs.append(perf_counter() - started)
                    assert response.status_code == 200, response.text
                report["seconds"][name] = round(min(runs), 4)
                report["bytes"][name] = len(response.content)
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
