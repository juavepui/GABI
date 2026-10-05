"""Published inputs, the old DSR bar and the report file for `gabi_cli research power-analysis` (#39)."""
import json
from pathlib import Path

import pandas as pd

from gabi.domain.research import power_analysis


def run(root: Path) -> dict:
    from gabi import factor_stability as fs
    from gabi import stats_rigor

    inputs = root / "docs" / "historical-revalidation-2011-2025" / "acreditado-38-continua"
    periods_path, bench_path = inputs / "v1-top20-periods.csv", inputs / "benchmarks-by-period.csv"
    prior = json.loads((root / "docs" / "overfitting-audit" / "audit.json").read_text(encoding="utf-8"))
    sharpes = [s["sharpe_anualizado"] for s in prior["including_cost_sensitivity"]["trial_statistics"].values()]
    sr0 = stats_rigor.expected_max_sharpe(sharpes, n_trials=power_analysis.DOCUMENTED_TRIALS)
    report = power_analysis.report(pd.read_csv(periods_path), pd.read_csv(bench_path), sr0)
    report["code_sha256"] = fs.content_hash(Path(power_analysis.__file__))
    report["inputs_sha256"] = {p.name: fs.content_hash(p) for p in (periods_path, bench_path)}
    report = fs._json_safe(report)
    output = root / "docs" / "power-analysis"
    output.mkdir(parents=True, exist_ok=True)
    (output / "power.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report
