"""Entry points of the 2010-2015 validation and the 2011-2025 revalidation for `gabi_cli research`.

Explicit commands: they prepare frozen snapshots, run backtests and write the
published folders. The engines stay in the old modules, which the frozen research
engines import; ``config.DB_PATH`` is only redirected inside their analysis, as before.
"""
from pathlib import Path


def validation(cache: Path | None, output: Path | None, analysis_only: bool) -> dict:
    from gabi import factor_stability as fs
    from gabi import historical_validation as hv

    report = hv.run(cache or hv.CACHE, output or hv.OUTPUT, analysis_only=analysis_only)
    return fs._json_safe(report["historical_validation"])


def revalidation_summary(report: dict) -> dict:
    from gabi import factor_stability as fs

    return fs._json_safe(report.get("historical_validation", {}).get("summary", {}))


def revalidation_analysis(view: str) -> dict:
    from gabi import historical_revalidation as hr

    return revalidation_summary(hr.evaluate(view, analysis_only=True))


def revalidation_prepare(variant: str) -> dict:
    from gabi import historical_revalidation as hr

    return {"variant": variant, "dates": len(hr.prepare(variant)["dates"])}


def revalidation_evaluate(view: str) -> dict:
    from gabi import historical_revalidation as hr

    return revalidation_summary(hr.evaluate(view))


def revalidation_overview() -> dict:
    from gabi import factor_stability as fs
    from gabi import historical_revalidation as hr

    return fs._json_safe(hr.summarize())

