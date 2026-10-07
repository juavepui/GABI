"""Compare full catalogue reads and cached invalidation over copied publications."""
import argparse
import shutil
import statistics
import subprocess
import tempfile
import time
import tracemalloc
from pathlib import Path
from types import ModuleType, SimpleNamespace

from gabi.infrastructure.storage.evidence_catalog import FileEvidenceCatalog
from gabi.infrastructure.storage.published_factors import FilePublishedFactors


def measured(call, repeats):
    durations, peaks = [], []
    for _ in range(repeats):
        tracemalloc.start()
        start = time.perf_counter()
        result = call()
        durations.append(time.perf_counter() - start)
        peaks.append(tracemalloc.get_traced_memory()[1] / 1024**2)
        tracemalloc.stop()
        assert result["available"]
    return statistics.median(durations), max(peaks)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", default="486942a")
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("repeats must be positive")
    root = Path(__file__).resolve().parents[1]
    source = subprocess.check_output(["git", "show", f"{args.baseline}:backend/src/gabi/evidence_catalog.py"],
                                     cwd=root).decode("utf-8")
    original = ModuleType("gabi._catalogue_measurement")
    original.__package__ = "gabi"
    exec(compile(source, "catalogue-baseline", "exec"), original.__dict__)
    with tempfile.TemporaryDirectory(prefix="catalogue_measure_", dir=root) as directory:
        copied = Path(directory)
        for path in FilePublishedFactors(root)._paths():
            if path.is_relative_to(root / "docs"):
                target = copied / path.relative_to(root)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)
        reader = FileEvidenceCatalog(copied)
        original.config = SimpleNamespace(BASE_DIR=copied)
        # Both variants verify the identical copied SIC artifacts with the F6 verifier.
        # Only the private baseline namespace is adapted; no global config changes.
        original.factor_sector_stability = SimpleNamespace(load_saved=reader.verify_sector)
        expected = original.load()
        assert reader.load() == expected
        old = measured(original.load, args.repeats)

        def cold():
            return FileEvidenceCatalog(copied).load()

        new_cold = measured(cold, args.repeats)
        cached = measured(reader.load, args.repeats)
        assert cold() == reader.load() == expected
        print(f"repeats={args.repeats} exact_parity=True")
        for name, (seconds, peak) in (("old", old), ("new_cold", new_cold), ("new_cached", cached)):
            print(f"{name}: median_seconds={seconds:.4f} peak_python_mib={peak:.3f}")


if __name__ == "__main__":
    main()
