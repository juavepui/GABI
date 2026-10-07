"""Queue scheduled tasks and run the separate local worker.

Usage: python -m gabi_cli serve | worker | schedule daily | schedule tiingo | periodic <options> | research <command>
"""

import argparse
import os
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from datetime import UTC, date, datetime
from functools import partial
from pathlib import Path

from gabi.application.administration.jobs import JobCommand, Jobs
from gabi.application.errors import QueryError
from gabi.application.market.insider_sync import sync_insiders
from gabi.application.research.academic_factors import prepare_factor_snapshot
from gabi.domain.market.selection import RankingFilter
from gabi.infrastructure.jobs.worker import Worker
from gabi.infrastructure.legacy.insiders import SecInsiders, classify_error, sec_user_agent
from gabi.infrastructure.legacy.jobs import LegacyExecutor
from gabi.infrastructure.providers.academic_factors import FrenchFactorSource
from gabi.infrastructure.settings import Settings
from gabi.infrastructure.storage.academic_factors import FileFactorCache
from gabi.infrastructure.storage.insiders import SqliteInsiders
from gabi.infrastructure.storage.jobs import SqliteJobs
from gabi_api.bootstrap import create_app
from gabi_cli.sources.bootstrap import build_fred_operation, build_tiingo_operations


def warm_rankings(app) -> None:
    """Read-only: build the frozen ranking (home, cartera) and the active model's one (Mercado)."""
    try:
        app.state.home.summary(compute=True)
        app.state.market.ranking(RankingFilter(hide_no_data=False), limit=1)
    except QueryError:
        pass  # No cached data yet: the pages show their own empty state.


def build_executor(settings: Settings, *, now: Callable[[], datetime] | None = None) -> LegacyExecutor:
    clock = now or (lambda: datetime.now(UTC))
    source = SecInsiders(sec_user_agent())
    store = SqliteInsiders(settings.data_dir, now=clock)
    insiders = partial(sync_insiders, source=source, store=store, classify_error=classify_error, now=clock)
    factors = partial(prepare_factor_snapshot, FileFactorCache(settings.data_dir), FrenchFactorSource())
    tiingo_fetch, tiingo_import = build_tiingo_operations(settings, now=clock)
    return LegacyExecutor(settings, insider_sync=insiders, factor_loader=factors,
                          tiingo_fetch=tiingo_fetch, tiingo_import=tiingo_import,
                          macro_sync=build_fred_operation(settings, now=clock))


def main() -> None:
    if sys.argv[1:2] == ["periodic"]:
        from gabi.infrastructure.legacy.periodic import build_periodic_tasks
        from gabi_cli.commands.periodic import main as periodic

        settings = Settings.from_environment()
        tiingo_fetch, tiingo_import = build_tiingo_operations(settings)
        periodic(build_periodic_tasks(settings.data_dir, tiingo_fetch=tiingo_fetch, tiingo_import=tiingo_import,
                                      macro_sync=build_fred_operation(settings)), sys.argv[2:])
        return
    if sys.argv[1:2] == ["research"]:
        from gabi_cli.research.bootstrap import main as research

        research(sys.argv[2:])
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["serve", "worker", "schedule"])
    parser.add_argument("kind", nargs="?", choices=["daily", "tiingo"])
    parser.add_argument("--once", action="store_true", help="Procesa un trabajo y termina")
    parser.add_argument("--force", action="store_true", help="Permite encolar Tiingo fuera del día 2")
    args = parser.parse_args()
    settings = Settings.from_environment()
    if args.action == "serve":
        import uvicorn

        configured_dist = os.environ.get("GABI_FRONTEND_DIST")
        dist = Path(configured_dist) if configured_dist else settings.data_dir.parent / "frontend" / "dist"
        if not (dist / "index.html").is_file():
            parser.error("Falta el build React; ejecuta npm --prefix frontend run build.")
        worker_process = subprocess.Popen([sys.executable, "-m", "gabi_cli", "worker"])
        app = create_app(settings, frontend_dist=dist)
        # The first ranking takes about a minute with a full cache: compute it while the server starts.
        threading.Thread(target=warm_rankings, args=(app,), name="gabi-warm-ranking", daemon=True).start()
        try:
            uvicorn.run(app, host="127.0.0.1", port=8000, access_log=False)
        finally:
            worker_process.terminate()
            try:
                worker_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                worker_process.kill()
                worker_process.wait()
        return
    store = SqliteJobs(settings.data_dir)
    if args.action == "schedule":
        if args.kind is None:
            parser.error("schedule necesita daily o tiingo")
        today = date.today()
        if args.kind == "tiingo" and today.day != 2 and not args.force:
            return
        jobs = Jobs(store)
        commands: tuple[tuple[JobCommand, str], ...]
        if args.kind == "daily":
            commands = ((JobCommand("refresh"), f"schedule:refresh:{today}"),
                        (JobCommand("maintenance"), f"schedule:maintenance:{today}"))
        else:
            commands = ((JobCommand("tiingo"), f"schedule:tiingo:{today:%Y-%m}"),)
        for command, key in commands:
            try:
                jobs.submit(command, key, origin="scheduler")
            except QueryError as exc:
                if exc.code != "job_conflict":
                    raise
        return
    worker = Worker(store, build_executor(settings), settings.data_dir)
    if args.once:
        worker.run_once()
        return
    while True:
        if not worker.run_once():
            time.sleep(2)
