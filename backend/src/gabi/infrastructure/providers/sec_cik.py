"""Current SEC ticker map downloaded only by an explicit refresh command."""

import json

import requests

URL = "https://www.sec.gov/files/company_tickers.json"


class SecTickerMap:
    def __init__(self, user_agent: str, *, max_bytes: int = 16 * 1024 * 1024, max_rows: int = 50000):
        self.user_agent, self.max_bytes, self.max_rows = user_agent, max_bytes, max_rows

    def fetch(self) -> dict:
        with requests.get(URL, headers={"User-Agent": self.user_agent}, timeout=20, stream=True) as response:
            response.raise_for_status()
            chunks, size = [], 0
            for chunk in response.iter_content(64 * 1024):
                size += len(chunk)
                if size > self.max_bytes:
                    raise ValueError("El mapa SEC supera el límite de bytes.")
                chunks.append(chunk)
            payload = json.loads(b"".join(chunks))
        if not isinstance(payload, dict):
            raise ValueError("Respuesta JSON del mapa SEC inválida.")
        if len(payload) > self.max_rows:
            raise ValueError("El mapa SEC supera el límite de filas.")
        return payload
