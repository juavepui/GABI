"""Loopback test API. No real configuration, credentials, database or network sources."""
import sys
import threading
import time
from pathlib import Path
from tempfile import TemporaryDirectory, gettempdir

import uvicorn

from gabi.infrastructure.jobs.worker import Worker
from gabi.infrastructure.settings import Settings
from gabi.infrastructure.storage.jobs import SqliteJobs
from gabi_api.bootstrap import create_app

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend" / "tests"))
from market_fixture import TODAY, seed_fixture  # noqa: E402


def main():
    with TemporaryDirectory(prefix="gabi-react-e2e-") as directory:
        root = Path(directory).resolve()
        assert root.is_relative_to(Path(gettempdir()).resolve())
        seed_fixture(root)
        app = create_app(Settings(root), today=lambda: TODAY)
        worker = Worker(SqliteJobs(root), lambda command: synthetic_job(command), root)
        threading.Thread(target=lambda: work_forever(worker), daemon=True).start()
        uvicorn.run(app, host="127.0.0.1", port=8001, log_level="warning")


def synthetic_job(command):
    time.sleep(0.5)
    if command.kind == "quality":
        return {"universe": 2, "sources": {"prices": {"covered": 2, "total": 2},
                                            "fundamentals": {"covered": 1, "total": 2}}}
    return {"fixture": True, "kind": command.kind}


def work_forever(worker):
    while True:
        if not worker.run_once():
            time.sleep(0.1)


if __name__ == "__main__":
    main()
