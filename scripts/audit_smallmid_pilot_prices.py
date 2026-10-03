"""Read-only #44 pilot price-coverage audit; never loads rankings or returns.

The original pilot checked Tiingo listing metadata. This script independently
counts the pilot CIKs with a downloaded series that passed the preregistered
SEC price-level rule in the current #44 data-collection snapshot. Its 92-day
column requires a continuous series and does not resolve terminal events.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

SOURCES = ("yahoo", "tiingo", "wiki", "kaggle")
KAGGLE_LAST_REBALANCE = "2021-01-02"
ROOT = Path(__file__).resolve().parents[1]


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def accepted_source(checks: list[dict[str, str]], day: str, through: str, kaggle_allowed: bool) -> str | None:
    """Apply the published #44 series/level gate to availability only."""
    low = (date.fromisoformat(day) - timedelta(days=400)).isoformat()
    for source in SOURCES:
        if source == "kaggle" and (not kaggle_allowed or day > KAGGLE_LAST_REBALANCE):
            continue
        own = [row for row in checks if row["fuente"] == source and row["desde"] <= low and row["hasta"] >= through]
        window = [row for row in own if low <= row["float_date"] <= day]
        if any(row["outcome"] == "passed" for row in window) and not any(row["outcome"] == "failed" for row in window):
            return source
    return None


def audit(sample_path: Path, checks_path: Path, agreement_path: Path) -> dict:
    sample = _rows(sample_path)
    checks_by_cik: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in _rows(checks_path):
        checks_by_cik[row["cik"]].append(row)
    agreement = json.loads(agreement_path.read_text(encoding="utf-8"))
    kaggle_allowed = agreement.get("aceptado") is True
    groups: dict[tuple[str, str], dict[str, int]] = defaultdict(
        lambda: {"n": 0, "tiingo_listing_candidate": 0, "level_passed_at_date": 0, "continuous_series_92_days": 0}
    )
    seen: set[tuple[str, str]] = set()
    for row in sample:
        day, cik = row["fecha"], row["cik"]
        if (day, cik) in seen:
            raise ValueError(f"duplicate pilot CIK/date: {cik} {day}")
        seen.add((day, cik))
        group = groups[(day, row["sigue_presentando_18m"])]
        group["n"] += 1
        group["tiingo_listing_candidate"] += int(
            row["tiingo_ticker_actual_cubre_ventana"] == "True"
            or row["tiingo_ticker_recuperado_cubre_ventana"] == "True"
        )
        own = checks_by_cik[cik]
        group["level_passed_at_date"] += int(accepted_source(own, day, day, kaggle_allowed) is not None)
        end = (date.fromisoformat(day) + timedelta(days=92)).isoformat()
        group["continuous_series_92_days"] += int(accepted_source(own, day, end, kaggle_allowed) is not None)
    return {
        "scope": "availability only; no ranks, returns, or terminal-event attribution",
        "inputs_sha256": {
            "sample": _sha256(sample_path),
            "level_checks": _sha256(checks_path),
            "kaggle_agreement": _sha256(agreement_path),
        },
        "kaggle_agreement_accepted": kaggle_allowed,
        "groups": {
            f"{day}_{'reporting' if reporting == 'True' else 'stopped_reporting'}": counts
            for (day, reporting), counts in sorted(groups.items())
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sample",
        type=Path,
        default=ROOT / "docs/smallmid-feasibility/muestra-cobertura.csv",
    )
    parser.add_argument("--checks", type=Path, default=ROOT / "data/smallmid_test/level_checks.csv")
    parser.add_argument("--agreement", type=Path, default=ROOT / "data/smallmid_test/kaggle_agreement.json")
    parser.add_argument("--output", type=Path, help="Optional report path; no data files are changed")
    args = parser.parse_args()
    result = audit(args.sample, args.checks, args.agreement)
    content = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(content, encoding="utf-8")
    else:
        print(content, end="")


if __name__ == "__main__":
    main()
