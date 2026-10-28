"""Read-only market audits.

Usage: python -m gabi_cli market checklist-coverage [--output FILE] [--reference FILE] [--symbols A,B]
"""

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path

from gabi.application.market.checklist_coverage import ChecklistReader, checklist_coverage


def main(checklist: ChecklistReader, universe: Callable[[], list[tuple[str, str]]], argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="gabi_cli market", description=__doc__)
    parser.add_argument("action", choices=["checklist-coverage"])
    parser.add_argument("--output", type=Path, help="Guarda el informe JSON en este fichero")
    parser.add_argument("--reference", type=Path,
                        help="Guarda la referencia de tasas de cumplimiento (#171) en este fichero")
    parser.add_argument("--symbols", help="Limita la auditoría a estos símbolos, separados por comas")
    args = parser.parse_args(argv)
    members = universe()
    if args.symbols:
        wanted = {symbol.strip().upper() for symbol in args.symbols.split(",") if symbol.strip()}
        members = [member for member in members if member[0] in wanted]

    def progress(done: int, total: int) -> None:
        if done % 50 == 0 or done == total:
            print(f"{done}/{total}", file=sys.stderr, flush=True)

    report = checklist_coverage(checklist, members, progress)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    if args.reference:
        args.reference.parent.mkdir(parents=True, exist_ok=True)
        args.reference.write_text(json.dumps(report["reference"], ensure_ascii=False, separators=(",", ":")) + "\n",
                                  encoding="utf-8")
    share = report["revenue_share"]
    print(f"Ingresos SEC en {report['non_financial_issuers'] - len(report['without_revenue'])}/"
          f"{report['non_financial_issuers']} emisores no financieros"
          + (f" ({share:.1%})" if share is not None else ""), file=sys.stderr)
