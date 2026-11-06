"""Inspect local maintenance status or explicitly run maintenance/downloads.

python -m gabi_cli periodic --status
python -m gabi_cli periodic --run [--no-refresh] [--full-refresh]
python -m gabi_cli periodic --tiingo
python -m gabi_cli periodic --motor     # métricas del motor probado de hoy (#347)
"""

import argparse
import json

from gabi.application.administration.periodic import PeriodicTasks
from gabi.domain.research.live_ledger import safe


def main(service: PeriodicTasks, argv: list[str]) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--no-refresh", action="store_true", help="Con --run: no refrescar datos antes")
    parser.add_argument("--tiingo", action="store_true")
    parser.add_argument("--motor", action="store_true",
                        help="Calcula y guarda hoy las métricas de empresa del motor probado (GABI-MF-v5, #347)")
    parser.add_argument("--full-refresh", action="store_true", help="Con --run: auditoría completa deliberada de las fuentes")
    args = parser.parse_args(argv)
    if args.run:
        report = service.run(refresh=not args.no_refresh, full_refresh=args.full_refresh)
        print(json.dumps(safe(report), ensure_ascii=False, indent=2))
        if report.get("error") or "ERROR" in (report.get("ledger", {}).get("status"),
                                              report.get("ledger_activo", {}).get("status")):
            raise SystemExit(1)
    elif args.motor:
        report = service.engine_fundamentals()
        print(json.dumps(safe(report), ensure_ascii=False, indent=2))
        if "error" in report:
            raise SystemExit(1)
    elif args.tiingo:
        print(json.dumps(safe(service.resume_tiingo()), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(safe(service.status()), ensure_ascii=False, indent=2))
