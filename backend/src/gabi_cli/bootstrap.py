"""Queue scheduled tasks and run the separate local worker.

Usage: python -m gabi_cli worker | schedule daily | schedule tiingo
"""

import argparse
import time
from datetime import date

from gabi.application.administration.jobs import JobCommand, Jobs
from gabi.application.errors import QueryError
from gabi.infrastructure.jobs.worker import Worker
from gabi.infrastructure.legacy.jobs import LegacyExecutor
from gabi.infrastructure.settings import Settings
from gabi.infrastructure.storage.jobs import SqliteJobs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["worker", "schedule"])
    parser.add_argument("kind", nargs="?", choices=["daily", "tiingo"])
    parser.add_argument("--once", action="store_true", help="Procesa un trabajo y termina")
    parser.add_argument("--force", action="store_true", help="Permite encolar Tiingo fuera del día 2")
    args = parser.parse_args()
    settings = Settings.from_environment()
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
    worker = Worker(store, LegacyExecutor(settings), settings.data_dir)
    if args.once:
        worker.run_once()
        return
    while True:
        if not worker.run_once():
            time.sleep(2)
