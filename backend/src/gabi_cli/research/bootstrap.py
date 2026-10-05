"""Reproducible research commands (ADR 0002).

Usage: python -m gabi_cli research <command> [arguments]
"""

import argparse
import json
import sys
from pathlib import Path

from gabi.infrastructure.settings import Settings


def sec_reconciliation(settings: Settings, args: argparse.Namespace) -> None:
    from gabi.infrastructure.legacy.sec_validation import run_reconciliation

    print(json.dumps(run_reconciliation(settings.data_dir), indent=2))


def legacy_filings(settings: Settings, args: argparse.Namespace) -> None:
    from gabi.infrastructure.legacy.sec_validation import run_legacy_pilot

    print(json.dumps(run_legacy_pilot(settings.data_dir), indent=2))


def power_analysis(settings: Settings, args: argparse.Namespace) -> None:
    from gabi.infrastructure.legacy.power_analysis import run

    print(json.dumps(run(settings.data_dir.parent), ensure_ascii=False, indent=2))


def historical_sec_audit(settings: Settings, args: argparse.Namespace) -> None:
    from gabi.infrastructure.legacy.historical_sec_audit import run

    docs = settings.data_dir.parent / "docs"
    values = run(settings.data_dir / "gabi.db", args.csv or docs / "historical-sec-2010-2015.csv",
                 args.json or docs / "historical-sec-2010-2015.json")
    print(json.dumps(values, ensure_ascii=False, indent=2))


def ledger(settings: Settings, args: argparse.Namespace) -> None:
    from gabi.infrastructure.storage import search_ledger

    root = settings.data_dir.parent
    if args.verify:
        search_ledger.verify(root)
        print("Published search ledger and source fingerprints verified (history remains incomplete).")
    else:
        print(json.dumps(search_ledger.write(root, args.write)["counts"]))


def frozen(settings: Settings, args: argparse.Namespace) -> None:
    from gabi.infrastructure import frozen_research

    try:
        if args.check_frozen:
            frozen_research.verify_frozen()
            frozen_research.verify_relocated_engines()
            print(f"{len(frozen_research.FROZEN)} frozen CI engines and 18 relocated published engines/config verified.")
        else:
            sys.exit(frozen_research.typecheck())
    except (OSError, ValueError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)


def main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="python -m gabi_cli research", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("sec-reconciliation", help="Concilia SEC NUM con los hechos exactos (validación 1996-2015)")
    command.set_defaults(run=sec_reconciliation)
    command = commands.add_parser("legacy-filings", help="Importa el piloto pre-XBRL revisado (descarga los 3 documentos fijados)")
    command.set_defaults(run=legacy_filings)
    command = commands.add_parser("power-analysis", help="Potencia estadística con resultados ya publicados (#39); escribe docs/power-analysis")
    command.set_defaults(run=power_analysis)
    command = commands.add_parser("historical-sec-audit", help="Cobertura SEC 2010-2015 de los miembros históricos (solo lee SQLite)")
    command.add_argument("--csv", type=Path, help="Por defecto docs/historical-sec-2010-2015.csv")
    command.add_argument("--json", type=Path, help="Por defecto docs/historical-sec-2010-2015.json")
    command.set_defaults(run=historical_sec_audit)
    command = commands.add_parser("ledger", help="Verifica el registro de búsquedas publicado o escribe una revisión nueva")
    actions = command.add_mutually_exclusive_group(required=True)
    actions.add_argument("--write", type=Path, help="Destino nuevo; nunca sobrescribe un registro publicado")
    actions.add_argument("--verify", action="store_true")
    command.set_defaults(run=ledger)
    command = commands.add_parser("frozen", help="Motores congelados intactos y mypy sin diagnósticos nuevos (CI)")
    actions = command.add_mutually_exclusive_group(required=True)
    actions.add_argument("--check-frozen", action="store_true")
    actions.add_argument("--typecheck", action="store_true")
    command.set_defaults(run=frozen)
    args = parser.parse_args(argv)
    args.run(Settings.from_environment(), args)
