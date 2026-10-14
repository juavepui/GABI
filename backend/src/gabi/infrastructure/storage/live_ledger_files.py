"""Single-writer lock and atomic head anchor of the live ledger, outside SQLite."""

import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def writer_lock(directory: Path) -> Iterator[None]:
    """Non-blocking exclusive lock on ``directory/writer.lock``; a second writer fails at once."""
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "writer.lock").open("a+b") as lock:
        lock.seek(0, os.SEEK_END)
        if lock.tell() == 0:
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        if sys.platform == "win32":
            import msvcrt
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            getattr(fcntl, "flock")(lock.fileno(), getattr(fcntl, "LOCK_EX") | getattr(fcntl, "LOCK_NB"))
        try:
            yield
        finally:
            lock.seek(0)
            if sys.platform == "win32":
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                getattr(fcntl, "flock")(lock.fileno(), getattr(fcntl, "LOCK_UN"))


def write_anchor(path: Path, text: str) -> None:
    """Durable replace: write and fsync a sibling file, then rename it over ``path``."""
    pending = path.with_suffix(".json.tmp")
    with pending.open("w", encoding="utf-8") as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())
    pending.replace(path)
