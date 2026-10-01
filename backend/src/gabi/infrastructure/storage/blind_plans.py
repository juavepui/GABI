"""Published blind-validation plans, verified once per file change."""

import threading
from pathlib import Path

from gabi.application.errors import QueryError
from gabi.infrastructure.legacy import blind_plans as legacy

READERS = ((legacy.GABI_PLAN, legacy.gabi_plan), (legacy.VALUE_PLAN, legacy.value_plan))


class FileBlindPlans:
    """Plans by validation id. A plan that exists but fails verification blocks every blind
    operation (503) instead of silently dropping its rules."""

    def __init__(self, root: Path):
        self.root = root
        self._lock = threading.Lock()
        self._cache: tuple[tuple, dict[int, dict]] | None = None

    def _stamp(self) -> tuple:
        stamps: list[tuple[int, int, int] | None] = []
        for relative, _ in READERS:
            try:
                stat = (self.root / relative).stat()
                stamps.append((stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns))
            except FileNotFoundError:
                stamps.append(None)
        return tuple(stamps)

    def plans(self) -> dict[int, dict]:
        with self._lock:
            stamp = self._stamp()
            if self._cache is None or self._cache[0] != stamp:
                plans = {}
                try:
                    for (relative, reader), present in zip(READERS, stamp, strict=True):
                        if present is not None:
                            plan = reader(self.root)
                            plans[plan["validation_id"]] = plan
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    raise QueryError("blind_plan_invalid",
                                     f"No se puede verificar el preregistro de las pruebas ciegas: {exc}", 503) from exc
                self._cache = (stamp, plans)
            return self._cache[1]
