"""HTTP documents used only during an explicit Form 4 job."""

import requests


class SecForm4Documents:
    def __init__(self, user_agent: str):
        self.headers = {"User-Agent": user_agent}

    def submissions(self, cik: str) -> dict:
        response = requests.get(f"https://data.sec.gov/submissions/CIK{cik}.json", headers=self.headers, timeout=30)
        if response.status_code == 404:
            raise ValueError("SEC EDGAR no tiene historial de filings para esta empresa")
        response.raise_for_status()
        return response.json()

    def xml(self, url: str) -> str:
        response = requests.get(url, headers=self.headers, timeout=20)
        response.raise_for_status()
        return response.text
