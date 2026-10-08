"""Bounded SEC JSON downloads, closed before any SQLite operation."""

import json

import requests

from gabi.domain.market.sec_xbrl import normalize_cik


class SecXbrl:
    def __init__(self, user_agent: str, *, max_bytes: int = 64 * 1024 * 1024):
        self.user_agent, self.max_bytes = user_agent, max_bytes

    def _fetch(self, url: str, missing: str) -> dict:
        with requests.get(url, headers={"User-Agent": self.user_agent}, timeout=30, stream=True) as response:
            if response.status_code == 404:
                raise ValueError(missing)
            response.raise_for_status()
            chunks, size = [], 0
            for chunk in response.iter_content(64 * 1024):
                size += len(chunk)
                if size > self.max_bytes:
                    raise ValueError("La respuesta SEC supera el límite de bytes.")
                chunks.append(chunk)
            payload = json.loads(b"".join(chunks))
        if not isinstance(payload, dict):
            raise ValueError("Respuesta JSON SEC inválida.")
        return payload

    def submissions(self, cik: str) -> dict:
        return self._fetch(f"https://data.sec.gov/submissions/CIK{normalize_cik(cik)}.json",
                           "SEC EDGAR no tiene historial de filings para esta empresa")

    def companyfacts(self, cik: str) -> dict:
        return self._fetch(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{normalize_cik(cik)}.json",
                           "SEC EDGAR no tiene datos XBRL estructurados para esta empresa")
