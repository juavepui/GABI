"""The published signal comparison rule, without its global storage helpers."""

from gabi import signal_monitor


def compare_snapshots(previous, current, top_n: int, thresholds: dict) -> list[dict]:
    return signal_monitor.compare_snapshots(previous, current, top_n, thresholds)
