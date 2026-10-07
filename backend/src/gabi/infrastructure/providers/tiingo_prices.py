"""Bounded Tiingo prices; the key travels only in the Authorization header."""

import json
from collections.abc import Callable

import requests

from gabi.application.research.tiingo_prices import PriceResponse
from gabi.domain.research.tiingo_prices import PRICES_URL


class TiingoPrices:
    def __init__(self, key: Callable[[], str | None], *, max_bytes: int = 8_000_000):
        if max_bytes <= 0:
            raise ValueError("Invalid Tiingo response limit")
        self.key, self.max_bytes = key, max_bytes

    def request(self, symbol: str, first: str, last: str) -> PriceResponse:
        key = self.key()
        if not key:
            raise ValueError("Tiingo API key missing: set it in Configuración")
        ticker = symbol.replace(".", "-").lower()
        headers = {"Authorization": f"Token {key}", "Content-Type": "application/json"}
        try:
            with requests.get(PRICES_URL.format(ticker=ticker, start=first, end=last),
                              headers=headers, timeout=60, stream=True) as response:
                if response.status_code != 200:
                    return PriceResponse(status=response.status_code)
                data = bytearray()
                for chunk in response.iter_content(chunk_size=64_000):
                    if len(data) + len(chunk) > self.max_bytes:
                        raise ValueError("Tiingo response byte limit exceeded")
                    data.extend(chunk)
                body = bytes(data)
                return PriceResponse(200, body, json.loads(body))
        except requests.RequestException as exc:
            return PriceResponse(error_name=type(exc).__name__)
