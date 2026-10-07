"""Bounded WIKI HTTP responses; credentials stay in the request only."""

import json

import requests

from gabi.application.research.wiki_prices import FetchResponse
from gabi.domain.research.wiki_prices import COLUMNS, END_EXCLUSIVE, START, URL, wiki_ticker


class NasdaqWikiSource:
    def __init__(self, *, max_bytes: int = 8_000_000):
        if max_bytes <= 0:
            raise ValueError("Invalid WIKI response limit")
        self.max_bytes = max_bytes

    def request(self, symbol: str, api_key: str) -> FetchResponse:
        params = {"ticker": wiki_ticker(symbol), "date.gte": START, "date.lt": END_EXCLUSIVE,
                  "qopts.columns": COLUMNS, "api_key": api_key}
        try:
            with requests.get(URL, params=params, timeout=90, stream=True) as response:
                if response.status_code != 200:
                    return FetchResponse(status=response.status_code)
                data = bytearray()
                for chunk in response.iter_content(chunk_size=64_000):
                    if len(data) + len(chunk) > self.max_bytes:
                        raise ValueError("WIKI response byte limit exceeded")
                    data.extend(chunk)
                return FetchResponse(200, json.loads(data))
        except requests.RequestException as exc:
            # Exception messages/URLs can contain the key; only retain the type.
            return FetchResponse(error_name=type(exc).__name__)
