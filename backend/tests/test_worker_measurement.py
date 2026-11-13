"""A real separate worker and concurrent API reads, with tiny temporary inputs."""

import json
import subprocess
import sys
from pathlib import Path


def test_worker_api_measurement_has_exact_serial_concurrent_parity(tmp_path):
    root = Path(__file__).resolve().parents[2]
    output = tmp_path / "measurement.json"
    subprocess.run([sys.executable, str(root / "scripts/measure_worker_api.py"), "--companies", "2",
                    "--sessions", "253", "--output", str(output)], cwd=root, check=True,
                   capture_output=True, text=True, timeout=120)
    report = json.loads(output.read_text())
    assert all(report["checks"].values())
    for case in report["cases"].values():
        assert len(case["concurrent"]["concurrent_reads"]) == 6
        assert case["concurrent"]["artifact_bytes"] > 0
    assert report["cases"]["quality"]["concurrent"]["metrics"]["price_rows_written"] == 0
