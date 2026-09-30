"""Use the unchanged consensus-revision formula with bounded injected readers."""

from datetime import date
from pathlib import Path

from gabi.infrastructure.storage.estimates import SqliteEstimateAnalysis


def run_estimate_analysis(data_dir: Path, cutoff: date) -> dict:
    from gabi import estimates

    reader = SqliteEstimateAnalysis(data_dir, cutoff)
    return estimates.evaluate_estimate_revision_signal(
        cutoff=cutoff, batch_loader=reader.batches, snapshot_loader=reader.rows,
        price_loader=reader.prices_for_sessions,
    )
