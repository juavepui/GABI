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


def sec_facts(settings: Settings, args: argparse.Namespace) -> None:
    from gabi.application.market.sec_reads import issuer_snapshot
    from gabi.domain.research.prospective_plan import json_value
    from gabi.infrastructure.storage.sec_reads import SqliteSecReads

    result = issuer_snapshot(SqliteSecReads(settings.data_dir / "gabi.db"), args.cik, args.as_of, args.tag)
    print(json.dumps(json_value(result), ensure_ascii=False, allow_nan=False))


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


def tenk_extraction(settings: Settings, args: argparse.Namespace) -> None:
    from gabi.infrastructure.legacy.sec_validation import directory
    from gabi.infrastructure.legacy.tenk_extraction import run

    summary = run(settings.data_dir.parent, directory(settings.data_dir), args.subset)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def rotation_experiment(settings: Settings, args: argparse.Namespace) -> None:
    from gabi.infrastructure.legacy.rotation_experiment import run

    run(args.cache or settings.data_dir / "full_universe_audit",
        args.output or settings.data_dir.parent / "docs" / "rotation-experiment", args.resume)


def value_hypothesis(settings: Settings, args: argparse.Namespace) -> None:
    from gabi.infrastructure.legacy.value_hypothesis import preregister

    record = preregister(settings.data_dir.parent / "docs" / "value-hypothesis")
    print(json.dumps({"sha256": record["sha256"], "blind_validation_id": record["blind_validation_id"],
                      "plan": record["plan_secuencial"]}, ensure_ascii=False, indent=2))


def quarterly_coverage(settings: Settings, args: argparse.Namespace) -> None:
    from contextlib import closing

    import exchange_calendars as xcals

    from gabi.application.research.quarterly_coverage import publish
    from gabi.infrastructure.storage.quarterly_coverage import FileQuarterlyCoverage, SqliteQuarterlyCoverage
    from gabi.infrastructure.storage.readonly import connect_readonly

    directory = settings.data_dir / "history_refresh/validation_1996_2015"
    resources = Path(__file__).parents[2] / "gabi/resources"
    sessions = xcals.get_calendar("XNYS", start="1994-01-01", end="2016-01-01").sessions
    with closing(connect_readonly(args.db or settings.data_dir / "gabi.db")) as connection, \
            closing(connect_readonly(args.before or directory / "before_validation.db")) as before:
        reader = SqliteQuarterlyCoverage(connection, before, args.cik_map or settings.data_dir / "sec_cik_map.csv",
                                         resources / "historical_sources_1996_2015.json", resources / "legacy_filings_pilot.json")
        publish(reader, sessions, FileQuarterlyCoverage(args.output or directory / "coverage"),
                progress=lambda message: print(message, flush=True))


def historical_data_audit(settings: Settings, args: argparse.Namespace) -> None:
    from contextlib import closing

    from gabi.application.research.historical_data_audit import publish_audit
    from gabi.infrastructure.storage.historical_data_audit import CsvAnnualAudit, SqliteAnnualAudit
    from gabi.infrastructure.storage.readonly import connect_readonly

    output = args.output or settings.data_dir.parent / "docs/historical-data-audit.csv"
    membership = args.membership or settings.data_dir / "sp500_historical_membership.csv"
    old_detail = args.old_detail or settings.data_dir / "history_refresh/validation_1996_2015/coverage/company-quarter.csv"
    manifest = Path(__file__).parents[2] / "gabi/resources/historical_sources_1996_2015.json"
    with closing(connect_readonly(args.db or settings.data_dir / "gabi.db")) as connection:
        reader = SqliteAnnualAudit(connection, membership, old_detail, manifest)
        publish_audit(reader, CsvAnnualAudit(output), progress=lambda message: print(message, flush=True))
    print(output)


def prospective_plan(settings: Settings, args: argparse.Namespace) -> None:
    from gabi.application.research.prospective_plan import publish_plan
    from gabi.domain.research.prospective_plan import gabi_blind_plan, json_value, plan
    from gabi.infrastructure.statistics.prospective import ScipyNormalCDF
    from gabi.infrastructure.storage.prospective_plans import FileProspectivePlans

    record = gabi_blind_plan() if args.gabi else plan(cdf=ScipyNormalCDF())
    if args.write:
        writer = FileProspectivePlans(args.output or settings.data_dir.parent / "docs/prospective-plan")
        payload = publish_plan(record, writer, name="gabi-id1.json" if args.gabi else "plan.json")
    else:
        payload = {"plan": record}
    print(json.dumps(json_value(payload), ensure_ascii=False, indent=2))


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


def wiki_prices(settings: Settings, args: argparse.Namespace) -> None:
    import sqlite3
    import time
    from contextlib import closing

    from gabi.application.research.wiki_prices import fetch, import_cached
    from gabi.infrastructure.providers.wiki_prices import NasdaqWikiSource
    from gabi.infrastructure.storage.historical_prices import SqliteHistoricalPrices
    from gabi.infrastructure.storage.wiki_prices import FileWikiCache, nasdaq_key

    cache = FileWikiCache(args.cache or settings.data_dir / "history_refresh/nasdaq_wiki")
    report = {}
    if args.fetch:
        with args.fetch.open("rb") as stream:
            data = stream.read(settings.max_small_file_bytes + 1)
        if len(data) > settings.max_small_file_bytes:
            raise ValueError("WIKI symbol file limit exceeded")
        symbols = [line.strip().upper() for line in data.decode("utf8").splitlines() if line.strip()]
        report["fetch"] = fetch(symbols, cache, NasdaqWikiSource(), api_key=nasdaq_key(settings.data_dir),
                                wait=time.sleep, progress=lambda message: print(message, flush=True),
                                max_symbols=settings.max_symbols)
    if args.import_cached:
        with closing(sqlite3.connect(args.db or settings.data_dir / "gabi.db")) as connection:
            report["import"] = import_cached(cache, SqliteHistoricalPrices(connection))
    print(json.dumps(report, indent=2))


def tiingo_prices(settings: Settings, args: argparse.Namespace) -> None:
    from gabi_cli.sources.bootstrap import build_tiingo_operations

    download, import_prices = build_tiingo_operations(settings, window_name=args.window,
                                                    cache_directory=args.cache, database=args.db)
    report = {}
    if args.fetch:
        with args.fetch.open("rb") as stream:
            data = stream.read(settings.max_small_file_bytes + 1)
        if len(data) > settings.max_small_file_bytes:
            raise ValueError("Tiingo symbol file limit exceeded")
        symbols = [line.strip().upper() for line in data.decode("utf8").splitlines() if line.strip()]
        report["fetch"] = download(symbols)
    if args.import_cached:
        report["import"] = import_prices()
    print(json.dumps(report, indent=2))


def main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="python -m gabi_cli research", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("sec-facts", help="Consulta hechos SEC locales por CIK y fecha, sin descargar ni escribir")
    command.add_argument("--cik", required=True)
    command.add_argument("--as-of", required=True)
    command.add_argument("--tag", action="append", help="Filtra hechos; las métricas usan todos los conceptos")
    command.set_defaults(run=sec_facts)
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
    command = commands.add_parser("tenk-extraction", help="Piloto de extracción de 10-K sin XBRL (#41); descarga de SEC")
    command.add_argument("--subset", choices=["ajuste", "reserva"])
    command.set_defaults(run=tenk_extraction)
    command = commands.add_parser("rotation-experiment", help="Experimento de rotación sobre los rankings congelados (sin descargas)")
    command.add_argument("--cache", type=Path, help="Por defecto <datos>/full_universe_audit")
    command.add_argument("--output", type=Path, help="Por defecto docs/rotation-experiment; usar un directorio nuevo")
    command.add_argument("--resume", action="store_true")
    command.set_defaults(run=rotation_experiment)
    command = commands.add_parser("value-hypothesis", help="Preregistro de la hipótesis de valor (#43); comprueba uno existente")
    command.add_argument("--preregister", action="store_true", required=True)
    command.set_defaults(run=value_hypothesis)
    command = commands.add_parser("quarterly-coverage", help="Cobertura trimestral 1996-2015 sin red ni backtests; exportación explícita")
    command.add_argument("--db", type=Path)
    command.add_argument("--before", type=Path)
    command.add_argument("--cik-map", type=Path)
    command.add_argument("--output", type=Path)
    command.set_defaults(run=quarterly_coverage)
    command = commands.add_parser("historical-data-audit", help="Inventario anual local de cobertura; lectura SQLite y exportación CSV explícita")
    command.add_argument("--db", type=Path)
    command.add_argument("--membership", type=Path)
    command.add_argument("--old-detail", type=Path)
    command.add_argument("--output", type=Path)
    command.set_defaults(run=historical_data_audit)
    command = commands.add_parser("prospective-plan", help="Plan de análisis prospectivo (#42), sin leer resultados ciegos")
    command.add_argument("--write", action="store_true", help="Escribir el JSON del plan en el directorio de salida")
    command.add_argument("--gabi", action="store_true", help="Plan fijo de la prueba GABI id 1; por defecto, diseño secuencial")
    command.add_argument("--output", type=Path, help="Por defecto docs/prospective-plan del proyecto")
    command.set_defaults(run=prospective_plan)
    command = commands.add_parser("wiki-prices", help="Descarga WIKI reanudable e importación local explícita al archivo histórico")
    command.add_argument("--fetch", type=Path, help="Fichero con un símbolo por línea")
    command.add_argument("--import-cached", action="store_true")
    command.add_argument("--cache", type=Path)
    command.add_argument("--db", type=Path)
    command.set_defaults(run=wiki_prices)
    command = commands.add_parser("tiingo-prices", help="Descarga Tiingo reanudable e importación fijada con checkpoints explícitos")
    command.add_argument("--fetch", type=Path)
    command.add_argument("--import-cached", action="store_true")
    command.add_argument("--window", default="2010-2015", choices=["2010-2015", "2016-2025", "smallmid"])
    command.add_argument("--cache", type=Path)
    command.add_argument("--db", type=Path)
    command.set_defaults(run=tiingo_prices)
    command = commands.add_parser("frozen", help="Motores congelados intactos y mypy sin diagnósticos nuevos (CI)")
    actions = command.add_mutually_exclusive_group(required=True)
    actions.add_argument("--check-frozen", action="store_true")
    actions.add_argument("--typecheck", action="store_true")
    command.set_defaults(run=frozen)
    args = parser.parse_args(argv)
    args.run(Settings.from_environment(), args)
