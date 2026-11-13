"""Download a file whose SHA-256 was pinned in a manifest; never keep a mismatching copy."""
import hashlib
from pathlib import Path

import requests


def matches(path: Path, sha256: str) -> bool:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest() == sha256


def download_pinned(item: dict, directory: Path) -> Path:
    path = directory / item["filename"]
    if path.exists() and matches(path, item["sha256"]):
        return path
    temporary = path.with_suffix(".part")
    with requests.get(item["url"], stream=True, timeout=(20, 90)) as response:
        response.raise_for_status()
        with temporary.open("wb") as output:
            for chunk in response.iter_content(1024 * 1024):
                output.write(chunk)
    if not matches(temporary, item["sha256"]):
        raise ValueError(f"Source hash mismatch: {item['filename']}")
    temporary.replace(path)
    return path
