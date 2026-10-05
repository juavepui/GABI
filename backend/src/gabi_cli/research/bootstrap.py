"""Reproducible research commands (ADR 0002).

Usage: python -m gabi_cli research <command> [arguments]
"""

import argparse
import json

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


def main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="python -m gabi_cli research", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("sec-reconciliation", help="Concilia SEC NUM con los hechos exactos (validación 1996-2015)")
    command.set_defaults(run=sec_reconciliation)
    command = commands.add_parser("legacy-filings", help="Importa el piloto pre-XBRL revisado (descarga los 3 documentos fijados)")
    command.set_defaults(run=legacy_filings)
    command = commands.add_parser("power-analysis", help="Potencia estadística con resultados ya publicados (#39); escribe docs/power-analysis")
    command.set_defaults(run=power_analysis)
    args = parser.parse_args(argv)
    args.run(Settings.from_environment(), args)
