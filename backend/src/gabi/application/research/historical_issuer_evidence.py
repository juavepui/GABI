"""Listing evidence assembled from explicit local submissions and frame facts."""

from typing import Protocol

from gabi.domain.market.identity import normalize_cik
from gabi.domain.research import issuer_evidence


class IssuerFiles(Protocol):
    def submissions(self, cik: str) -> tuple[dict, list[dict]] | None: ...
    def issuer_facts(self, cik: str, frame_year_max: int | None = None) -> dict: ...


def listing_life(reader: IssuerFiles, cik: str, floatless_before: str,
                 frame_year_max: int | None = None) -> dict | None:
    cik = normalize_cik(cik)
    documents = reader.submissions(cik)
    if documents is None:
        return None
    payload, pages = documents
    return issuer_evidence.listing_life(cik, payload, pages, reader.issuer_facts(cik, frame_year_max),
                                       floatless_before)
