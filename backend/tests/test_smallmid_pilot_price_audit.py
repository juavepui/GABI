"""The #44 coverage audit reads only supplied temporary files."""

import csv
import json
import runpy
from pathlib import Path

_AUDIT = runpy.run_path(
    str(Path(__file__).resolve().parents[2] / "scripts/audit_smallmid_pilot_prices.py"),
    run_name="smallmid_pilot_audit",
)
accepted_source = _AUDIT["accepted_source"]
audit = _AUDIT["audit"]


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)


def test_price_gate_requires_a_level_pass_and_rejects_conflicts() -> None:
    row = {
        "fuente": "tiingo",
        "desde": "2015-01-01",
        "hasta": "2017-12-31",
        "float_date": "2017-01-01",
        "outcome": "passed",
    }
    assert accepted_source([row], "2017-06-30", "2017-09-30", False) == "tiingo"
    assert accepted_source([row | {"outcome": "missing"}], "2017-06-30", "2017-09-30", False) is None
    assert accepted_source([row, row | {"outcome": "failed"}], "2017-06-30", "2017-09-30", False) is None
    assert accepted_source([row | {"hasta": "2017-07-01"}], "2017-06-30", "2017-09-30", False) is None
    kaggle = row | {"fuente": "kaggle"}
    assert accepted_source([kaggle], "2017-06-30", "2017-09-30", False) is None
    assert accepted_source([kaggle], "2017-06-30", "2017-09-30", True) == "kaggle"
    kaggle_2022 = kaggle | {"desde": "2020-01-01", "hasta": "2022-12-31", "float_date": "2022-01-01"}
    assert accepted_source([kaggle_2022], "2022-06-30", "2022-06-30", True) is None


def test_audit_distinguishes_listing_from_validated_price_and_uses_temp_files(tmp_path: Path) -> None:
    sample, checks, agreement = (tmp_path / name for name in ("sample.csv", "checks.csv", "agreement.json"))
    _write_csv(
        sample,
        [
            {
                "fecha": "2017-06-30",
                "cik": "0000000001",
                "sigue_presentando_18m": "False",
                "tiingo_ticker_actual_cubre_ventana": "True",
                "tiingo_ticker_recuperado_cubre_ventana": "False",
            },
            {
                "fecha": "2017-06-30",
                "cik": "0000000002",
                "sigue_presentando_18m": "True",
                "tiingo_ticker_actual_cubre_ventana": "False",
                "tiingo_ticker_recuperado_cubre_ventana": "False",
            },
        ],
    )
    _write_csv(
        checks,
        [
            {
                "cik": "0000000001",
                "fuente": "wiki",
                "desde": "2015-01-01",
                "hasta": "2017-07-15",
                "float_date": "2017-01-01",
                "outcome": "passed",
            },
            {
                "cik": "0000000002",
                "fuente": "yahoo",
                "desde": "2015-01-01",
                "hasta": "2017-12-31",
                "float_date": "2017-01-01",
                "outcome": "passed",
            },
        ],
    )
    agreement.write_text(json.dumps({"aceptado": True}), encoding="utf-8")
    report = audit(sample, checks, agreement)
    assert report["groups"]["2017-06-30_stopped_reporting"] == {
        "n": 1,
        "tiingo_listing_candidate": 1,
        "level_passed_at_date": 1,
        "continuous_series_92_days": 0,
    }
    assert report["groups"]["2017-06-30_reporting"] == {
        "n": 1,
        "tiingo_listing_candidate": 0,
        "level_passed_at_date": 1,
        "continuous_series_92_days": 1,
    }
