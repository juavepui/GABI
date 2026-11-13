"""Published Research Lab audits, loaded and hash-verified by their unchanged legacy readers."""

from pathlib import Path


def load_overfitting(directory: Path):
    from gabi import overfitting_audit

    return overfitting_audit.load_audit(directory)


def load_factor_benchmark(directory: Path) -> dict:
    from gabi import factor_benchmark

    return factor_benchmark.load_audit(directory)


def load_factor_stability(directory: Path) -> dict:
    from gabi import factor_stability

    return factor_stability.load_audit(directory)


def load_block_bootstrap(directory: Path) -> dict:
    from gabi import block_bootstrap

    # The published reader has a fixed location; never read another directory under its name.
    if directory.resolve() != block_bootstrap.OUTPUT.resolve():
        raise ValueError("El diagnóstico de bloques solo se lee de su ubicación publicada.")
    return block_bootstrap.load_saved()


def load_rank_stability(directory: Path) -> dict:
    from gabi import rank_stability

    if directory.resolve() != rank_stability.OUTPUT.resolve():
        raise ValueError("La estabilidad histórica solo se lee de su ubicación publicada.")
    return rank_stability.load_saved()
