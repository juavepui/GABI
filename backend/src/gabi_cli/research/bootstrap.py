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


def entity_migration(settings: Settings, args: argparse.Namespace) -> None:
    from gabi.infrastructure.legacy import entity_migration as migration

    if args.attribute_symbol and not all((args.entity_id, args.dataset, args.source)):
        raise SystemExit("Attribution requires --entity-id, --dataset and --source evidence")
    if args.submissions_json and not all((args.candidate_symbol, args.historical_name, args.source)):
        raise SystemExit("Candidate import requires --candidate-symbol, --historical-name and --source")
    if args.migrate or args.activate_reviewed_symbol or args.attribute_symbol or args.submissions_json:
        migration.backup_once(settings.data_dir / "gabi.db")
    if args.migrate:
        print(json.dumps(migration.migrate(), indent=2))
    if args.activate_reviewed_symbol:
        print(json.dumps(migration.activate(args.activate_reviewed_symbol)))
    if args.attribute_symbol:
        print(migration.attribute_legacy(args.attribute_symbol, args.entity_id, args.dataset, source=args.source,
                                         start=args.start, end=args.end))
    if args.submissions_json:
        print(migration.import_candidates(args.candidate_symbol, args.historical_name, args.submissions_json, args.source))
    if args.report:
        report = migration.write_report(args.history or settings.data_dir / "sp500_historical_membership.csv",
                                        args.cik_map or settings.data_dir / "sec_cik_map.csv", args.report)
        print(json.dumps(report, indent=2))


def historical_backfill(settings: Settings, args: argparse.Namespace) -> None:
    from gabi.infrastructure.legacy import historical_backfill as backfill

    if args.import_prices:
        print(json.dumps(backfill.import_price_archive(settings.data_dir, *args.import_prices)))
    else:
        backfill.run(settings.data_dir)


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
    command = commands.add_parser("entity-migration", help="Migración aditiva de identidad y cobertura histórica (base de GABI_DATA_DIR)")
    command.add_argument("--migrate", action="store_true")
    command.add_argument("--activate-reviewed-symbol", help="Activate only a specifically reviewed ticker interval")
    command.add_argument("--report", type=Path)
    command.add_argument("--history", type=Path, help="Por defecto <datos>/sp500_historical_membership.csv")
    command.add_argument("--cik-map", type=Path, help="Por defecto <datos>/sec_cik_map.csv")
    command.add_argument("--attribute-symbol")
    command.add_argument("--entity-id")
    command.add_argument("--dataset", choices=["prices", "splits", "fundamentals", "edgar_facts"])
    command.add_argument("--source")
    command.add_argument("--start")
    command.add_argument("--end")
    command.add_argument("--submissions-json", type=Path)
    command.add_argument("--candidate-symbol")
    command.add_argument("--historical-name")
    command.set_defaults(run=entity_migration)
    command = commands.add_parser("historical-backfill", help="Archivo gratuito 1996-2015: descarga fuentes fijadas e importa (escritura explícita)")
    command.add_argument("--import-prices", nargs=2, metavar=("START", "END"),
                         help="Solo importa el archivo de precios ya descargado para [START, END) (#34)")
    command.set_defaults(run=historical_backfill)
    command = commands.add_parser("frozen", help="Motores congelados intactos y mypy sin diagnósticos nuevos (CI)")
    actions = command.add_mutually_exclusive_group(required=True)
    actions.add_argument("--check-frozen", action="store_true")
    actions.add_argument("--typecheck", action="store_true")
    command.set_defaults(run=frozen)
    args = parser.parse_args(argv)
    args.run(Settings.from_environment(), args)
