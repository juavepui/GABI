"""The existing SEC CIK resolver behind an explicit Form 4 ingestion port."""

import concurrent.futures as cf

from gabi.application.market.insider_sync import InsiderAttempt, fetch_transactions
from gabi.infrastructure.providers.form4 import SecForm4Documents


class SecInsiders:
    def __init__(self, user_agent: str):
        self.documents = SecForm4Documents(user_agent)

    @staticmethod
    def mapping():
        from gabi.edgar import get_cik_map

        return get_cik_map()

    @staticmethod
    def resolve(symbol, mapping):
        from gabi.edgar import get_cik_for_symbol

        return get_cik_for_symbol(symbol, cik_map=mapping)[0]

    def fetch(self, symbol: str, cik: str) -> list[dict]:
        return fetch_transactions(symbol, cik, self.documents)

    def attempts(self, ciks: dict[str, str], max_workers: int):
        with cf.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(self.fetch, symbol, cik): symbol for symbol, cik in ciks.items()}
            for future in cf.as_completed(futures):
                symbol = futures[future]
                try:
                    yield InsiderAttempt(symbol, rows=future.result())
                except Exception as exc:
                    yield InsiderAttempt(symbol, error=exc)


def classify_error(exc: Exception) -> str:
    from gabi.data_fetch import _classify_error

    return _classify_error(exc, service="SEC EDGAR")[1]


def sec_user_agent() -> str:
    from gabi.config import SEC_USER_AGENT

    return SEC_USER_AGENT
