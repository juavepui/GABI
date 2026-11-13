"""Bounded downloads of S&P 500 membership sources (GitHub CSVs and the Wikipedia list)."""

from io import BytesIO, StringIO

import pandas as pd
import requests

GITHUB_CSV_URL = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
HISTORICAL_MEMBERSHIP_URL = ("https://raw.githubusercontent.com/hanshof/sp500_constituents/main/"
                             "sp_500_historical_components.csv")


class SP500Sources:
    def __init__(self, user_agent: str, *, max_bytes: int = 32 * 1024 * 1024, timeout: float = 60):
        if max_bytes <= 0:
            raise ValueError("Invalid S&P 500 source limit")
        self.headers, self.max_bytes, self.timeout = {"User-Agent": user_agent}, max_bytes, timeout

    def fetch(self, url: str) -> bytes:
        data = bytearray()
        with requests.get(url, headers=self.headers, timeout=self.timeout, stream=True) as response:
            response.raise_for_status()
            for chunk in response.iter_content(64 * 1024):
                if len(data) + len(chunk) > self.max_bytes:
                    raise ValueError("La fuente del S&P 500 supera el límite de bytes.")
                data.extend(chunk)
        return bytes(data)

    def constituents_csv(self) -> pd.DataFrame:
        return pd.read_csv(BytesIO(self.fetch(GITHUB_CSV_URL)))

    def wikipedia_page(self) -> bytes:
        return self.fetch(WIKI_URL)

    @staticmethod
    def wikipedia_tables(page: bytes) -> list[pd.DataFrame]:
        return pd.read_html(StringIO(page.decode("utf-8", errors="replace")))

    def historical_membership(self) -> pd.DataFrame:
        return pd.read_csv(BytesIO(self.fetch(HISTORICAL_MEMBERSHIP_URL)), dtype={"date": str})
