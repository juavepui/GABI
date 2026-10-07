"""Bounded FRED responses; credentials never enter a logged HTTP error URL."""

import json
from datetime import date
from pathlib import Path

import requests

from gabi.domain.market.fred import RELEASE_IDS, observations, parse_next_release_date

BASE_URL = "https://api.stlouisfed.org/fred/series/observations"
RELEASE_URL = "https://api.stlouisfed.org/fred/release/dates"


def fred_key(data_dir: Path) -> str | None:
    path = data_dir / "fred_api_key.txt"
    if not path.is_file():
        return None
    with path.open("rb") as file:
        raw = file.read(4097)
    if len(raw) > 4096:
        raise ValueError("La clave FRED supera 4096 bytes.")
    return raw.decode().strip() or None


class FredSource:
    def __init__(self, *, max_bytes: int = 32 * 1024 * 1024, max_rows: int = 100000):
        self.max_bytes, self.max_rows = max_bytes, max_rows

    @staticmethod
    def _request(url: str, params: dict):
        try:
            return requests.get(url, params=params, timeout=20, stream=True)
        except requests.RequestException as exc:
            # requests includes credential-bearing URLs in some exception messages.
            raise type(exc)(type(exc).__name__) from None

    def _payload(self, url: str, params: dict, *, observations_request: bool = False) -> dict:
        with self._request(url, params) as response:
            if observations_request and response.status_code in (400, 401, 403):
                raise ValueError("FRED ha rechazado la petición (revisa que la API key sea correcta)")
            if response.status_code >= 400:
                raise requests.HTTPError(f"FRED HTTP {response.status_code}", response=response)
            chunks, size = [], 0
            for chunk in response.iter_content(64 * 1024):
                size += len(chunk)
                if size > self.max_bytes:
                    raise ValueError("La respuesta FRED supera el límite de bytes.")
                chunks.append(chunk)
            payload = json.loads(b"".join(chunks))
        if not isinstance(payload, dict):
            raise ValueError("Respuesta JSON FRED inválida.")
        return payload

    def fetch(self, series_id: str, api_key: str, units: str = "lin", limit: int = 260,
              *, observation_start: str | None = None, include_missing: bool = False) -> list:
        if not 1 <= limit <= self.max_rows:
            raise ValueError("La ventana FRED supera el límite de observaciones.")
        params = {"series_id": series_id, "api_key": api_key, "file_type": "json",
                  "sort_order": "desc", "limit": limit, "units": units}
        if observation_start:
            params["observation_start"] = observation_start
        payload = self._payload(BASE_URL, params, observations_request=True)
        rows = payload.get("observations", [])
        if len(rows) > limit or int(payload.get("count", len(rows))) > limit:
            raise ValueError("La respuesta FRED requiere paginación; checkpoint conservado.")
        return observations(payload, include_missing=include_missing)

    def next_release(self, series_id: str, api_key: str, today: date) -> date | None:
        release_id = RELEASE_IDS.get(series_id)
        if release_id is None:
            return None
        payload = self._payload(RELEASE_URL, {
            "release_id": release_id, "api_key": api_key, "file_type": "json",
            "realtime_start": today.isoformat(), "sort_order": "asc",
            "include_release_dates_with_no_data": "true"})
        if len(payload.get("release_dates", [])) > self.max_rows:
            raise ValueError("La respuesta FRED supera el límite de publicaciones.")
        return parse_next_release_date(payload, today)
