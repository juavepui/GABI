"""Entry point of the completed rotation experiment for `gabi_cli research rotation-experiment`.

The experiment patches the old backtest engines and points the old configuration at
a working copy of the frozen snapshot while it runs; that stays inside the old module
until #90 frees those engines. Its protocol and audit are sealed in the search ledger.
"""
from pathlib import Path


def run(cache: Path, output: Path, resume: bool) -> dict:
    from gabi.rotation_experiment import execute

    return execute(cache, output, resume=resume)
