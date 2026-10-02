import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    batch_size: int = 16
    max_symbols: int = 1000
    max_price_rows_per_batch: int = 160_000
    max_benchmark_rows: int = 10_000
    max_small_file_bytes: int = 1_000_000
    cache_entries: int = 4
    # The key already changes with date, weights, universe and SQLite revision; this is only an upper bound.
    cache_seconds: int = 12 * 3600
    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")

    def __post_init__(self) -> None:
        if not self.data_dir.is_absolute():
            raise ValueError("data_dir must be absolute")
        if any(value <= 0 for value in (self.batch_size, self.max_symbols, self.max_price_rows_per_batch,
                                       self.max_benchmark_rows, self.max_small_file_bytes,
                                       self.cache_entries, self.cache_seconds)) or self.max_symbols > 1000:
            raise ValueError("Invalid resource limits")
        allowed = {"http://localhost:5173", "http://127.0.0.1:5173"}
        if not set(self.cors_origins) <= allowed:
            raise ValueError("Only the local Vite origins are supported")

    @classmethod
    def from_environment(cls) -> "Settings":
        configured = os.environ.get("GABI_DATA_DIR")
        if configured:
            return cls(Path(configured))
        configured_root = os.environ.get("GABI_PROJECT_ROOT")
        if configured_root:
            return cls(Path(configured_root) / "data")
        for parent in Path(__file__).resolve().parents:
            if (parent / "backend/pyproject.toml").is_file() and (parent / "docs/architecture.md").is_file():
                return cls(parent / "data")
        raise ValueError("Set an absolute GABI_DATA_DIR outside a source checkout")
