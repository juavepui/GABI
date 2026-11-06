"""The active model's ranking saved by the daily task, so a restarted server does not rebuild it (#342).

Written only by an explicit action (``ReadOnlyMarket.save_snapshot``, run by the daily task), never by a query.
The file holds a one-line JSON header with the digest of the full cache key (ranking-input revision of #342,
date, weights, benchmark, risk-free rate, model and SEC metrics version) followed by the pickled
``RankingSnapshot``: the table must come back exactly (dtypes, NaN versus None, ``attrs``), which JSON does not
guarantee. The payload is unpickled only when the header matches the current key and the pandas version; any
mismatch, truncation or read error is a cache miss and the ranking is computed as before. Like gabi.db itself,
the file is trusted local data inside ``data/``.
"""

import hashlib
import json
import os
import pickle
from pathlib import Path

import pandas as pd

FORMAT = "gabi-ranking-snapshot-v1"
NAME = "ranking_snapshot.pkl"
MAX_BYTES = 256 * 1024 * 1024


def digest(key: tuple) -> str:
    return hashlib.sha256(repr(key).encode()).hexdigest()


def save(path: Path, key: tuple, snapshot) -> int:
    """Atomic replace: a reader sees the previous file or the new one, never half of it."""
    header = json.dumps({"format": FORMAT, "key": digest(key), "pandas": pd.__version__}).encode() + b"\n"
    payload = header + pickle.dumps(snapshot, protocol=pickle.HIGHEST_PROTOCOL)
    if len(payload) > MAX_BYTES:
        raise ValueError("El ranking guardado supera el límite de tamaño.")
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    return len(payload)


def load(path: Path, key: tuple):
    """The saved snapshot for exactly this key, or None."""
    try:
        if path.stat().st_size > MAX_BYTES:
            return None
        with path.open("rb") as stream:
            header = json.loads(stream.readline(4096))
            if header != {"format": FORMAT, "key": digest(key), "pandas": pd.__version__}:
                return None
            return pickle.loads(stream.read())
    except (OSError, ValueError, EOFError, pickle.UnpicklingError, AttributeError, ImportError, TypeError):
        return None
