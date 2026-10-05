"""Keep archived research immutable and reject new mypy diagnostics globally.

The exact 25 pre-existing diagnostics are recorded, not broad error categories.
Every invocation still runs mypy on the entire package with the normal config.
Paths are those of the installed checkout: ``backend`` holds ``src/gabi`` and the
engine manifest, its parent holds ``.github``.
"""

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[3]
ROOT = BACKEND.parent
FROZEN = {
    "src/gabi/tail_effect_test.py": "2c1216b53b7f45d4d57ef5e5cf8252771891fd816523ad917396079f5fc6fda3",
    "src/gabi/factor_zoo.py": "7783e6885410c6c89d374e3ce9251f565b5d1b810c9fff387b768f82e454ee07",
    "src/gabi/placebo_engine.py": "6cfe4f7ead369005a9fdf4c51ea1a984171bee895d179bf75a14d459b15493fc",
}


def verify_frozen(backend: Path = BACKEND) -> None:
    for relative, expected in FROZEN.items():
        # Git may use CRLF on Windows. Only line endings are normalized.
        actual = hashlib.sha256((backend / relative).read_text(encoding="utf-8").encode("utf-8")).hexdigest()
        if actual != expected:
            raise ValueError(f"Frozen research engine changed: {relative}; review its archived evidence and CI baseline.")


def verify_relocated_engines(backend: Path = BACKEND) -> None:
    manifest = json.loads((backend / "legacy-engine-hashes.json").read_text(encoding="utf-8"))
    for name, expected in manifest.items():
        actual = hashlib.sha256((backend / "src" / "gabi" / name).read_text(encoding="utf-8").encode()).hexdigest()
        if actual != expected:
            raise ValueError(f"Relocated published engine changed: {name}; preserve/version its archived evidence.")


def normalized(record: dict) -> str:
    value = {**record, "file": record["file"].replace("\\", "/")}
    for prefix in (BACKEND.as_posix() + "/", "backend/"):
        if value["file"].startswith(prefix + "src/gabi/"):
            value["file"] = value["file"][len(prefix):]
            break
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def diagnostic_differences(records: list[dict], baseline: list[dict]) -> tuple[Counter, Counter]:
    actual = Counter(normalized(record) for record in records)
    expected = Counter(normalized(record) for record in baseline)
    return actual - expected, expected - actual


def load_baseline(root: Path = ROOT) -> list[dict]:
    baseline = json.loads((root / ".github" / "mypy-baseline.json").read_text(encoding="utf-8"))
    if len(baseline) != 25 or any(record["file"] not in FROZEN or record["severity"] != "error" for record in baseline):
        raise ValueError("The mypy baseline must contain exactly the 25 archived-engine diagnostics.")
    return baseline


def typecheck() -> int:
    from mypy import api

    verify_frozen()
    baseline = load_baseline()
    output, errors, status = api.run([
        "--config-file", str(BACKEND / "pyproject.toml"), "--output=json", str(BACKEND / "src"),
    ])
    if errors:
        print(errors, file=sys.stderr, end="")
    if status not in (0, 1):
        print(output, end="")
        return status
    records = [json.loads(line) for line in output.splitlines() if line.strip()]
    added, removed = diagnostic_differences(records, baseline)
    if added or removed or errors or status != 1:
        for title, diagnostics in (("New mypy diagnostics", added), ("Baseline diagnostics changed/missing", removed)):
            if diagnostics:
                print(title + ":", file=sys.stderr)
                for diagnostic, count in diagnostics.items():
                    print(f"{count} x {diagnostic}", file=sys.stderr)
        return 1
    print(f"mypy checked backend/src: no new diagnostics; {len(baseline)} exact historical diagnostics in unchanged frozen engines.")
    return 0
