"""Read-only, hash-verified files of the #53 study; returns, SQLite and reserved tests are never opened."""

import hashlib
import json
from pathlib import Path

import pandas as pd

from gabi.domain.research.ensemble_robustness import fingerprint, json_ready

PREREGISTRATION = "docs/ensemble-robustness/preregistro.json"
SCORES = "docs/strategy-discovery/scores.csv"
SCORES_RESULT = "docs/strategy-discovery/resultado.json"
FACTOR_ZOO_RESULT = "docs/factor-zoo/resultado.json"
FACTOR_ZOO_SHA256 = "84f76e03bbe676d80ae5b0c4ae3af031b6a50fd23f7536b842e1f03df409bee0"
RANKINGS = "data/revalidation_2011_2025/acreditado-38"


def _bytes_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class PublishedEnsembleInputs:
    """Only the declared paths; every file hash is checked before its contents are parsed."""

    def __init__(self, root: Path, *, factor_zoo_sha256: str = FACTOR_ZOO_SHA256) -> None:
        self.root = root
        self.factor_zoo_sha256 = factor_zoo_sha256
        self.opened: list[str] = []
        self._ranking_hashes: dict[str, str] | None = None

    def _path(self, name: str) -> Path:
        if "forward-" in name or name.endswith((".db", ".sqlite")):
            raise PermissionError(f"Lectura prohibida por el preregistro de #53: {name}")
        self.opened.append(name)
        return self.root / name

    def _json(self, name: str) -> dict:
        return json.loads(self._path(name).read_text(encoding="utf-8"))

    def preregistration(self) -> dict:
        return self._json(PREREGISTRATION)

    def scores(self, columns: list[str]) -> pd.DataFrame:
        expected = self._json(SCORES_RESULT)["artifacts_sha256"]["scores.csv"]
        path = self._path(SCORES)
        if _bytes_hash(path) != expected:
            raise ValueError("scores.csv no coincide con la huella publicada por #60.")
        return pd.read_csv(path, usecols=columns, dtype={"fecha": str, "symbol": str, "entity_id": str,
                                                         "division": str},
                           keep_default_na=False, na_values=[""])

    def _rankings(self) -> dict[str, str]:
        if self._ranking_hashes is None:
            original = self._json(FACTOR_ZOO_RESULT)
            if fingerprint(original) != self.factor_zoo_sha256:
                raise ValueError("El resultado de #48 que acredita los rankings ha cambiado.")
            self._ranking_hashes = {
                Path(name.replace("\\", "/")).stem.removeprefix("ranking-"): digest
                for name, digest in original["inputs_sha256"].items()
                if Path(name.replace("\\", "/")).name.startswith("ranking-")}
        return self._ranking_hashes

    def risk(self, date: str, columns: list[str]) -> pd.DataFrame:
        expected = self._rankings().get(date)
        if expected is None:
            raise PermissionError(f"Ranking fuera de las 57 fechas acreditadas: {date}")
        path = self._path(f"{RANKINGS}/ranking-{date}.csv")
        if _bytes_hash(path) != expected:
            raise ValueError(f"Ranking congelado modificado: {date}")
        table = pd.read_csv(path, index_col="symbol", usecols=["symbol", "entity_id", *columns],
                            dtype={"symbol": str, "entity_id": str})
        if table.index.has_duplicates:
            raise ValueError(f"Símbolos duplicados en el ranking congelado: {date}")
        return table

    def fingerprints(self) -> dict:
        return {"scores_csv_sha256": self._json(SCORES_RESULT)["artifacts_sha256"]["scores.csv"],
                "factor_zoo_result_sha256": self.factor_zoo_sha256,
                "rankings_sha256": dict(sorted(self._rankings().items())),
                "files_opened": sorted(set(self.opened))}


def verify(root: Path, published: Path, scratch: Path, *, factor_zoo_sha256: str = FACTOR_ZOO_SHA256) -> dict:
    """Recompute into ``scratch`` and require the published canonical fingerprint."""
    from gabi.application.research.ensemble_robustness import analyze

    saved = json.loads((published / "resultado.json").read_text(encoding="utf-8"))
    if fingerprint({key: value for key, value in saved.items() if key != "sha256"}) != saved["sha256"]:
        raise ValueError("resultado.json publicado modificado.")
    for name, digest in saved["artifacts_sha256"].items():
        if _bytes_hash(published / name) != digest:
            raise ValueError(f"Artefacto publicado modificado: {name}")
    fresh = save(scratch, *analyze(PublishedEnsembleInputs(root, factor_zoo_sha256=factor_zoo_sha256)))
    if fresh["sha256"] != saved["sha256"]:
        raise ValueError("La reproducción no coincide con el resultado publicado de #53.")
    return fresh


def save(destination: Path, result: dict, tables: dict[str, pd.DataFrame]) -> dict:
    """Write a new result folder; never overwrite a published one."""
    destination.mkdir(parents=True, exist_ok=True)
    artifacts = {}
    for name, table in tables.items():
        path = destination / name
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            table.to_csv(stream, index=False, lineterminator="\n")
        artifacts[name] = _bytes_hash(path)
    payload = json_ready({**result, "artifacts_sha256": artifacts})
    payload["sha256"] = fingerprint(payload)
    with (destination / "resultado.json").open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    return payload
