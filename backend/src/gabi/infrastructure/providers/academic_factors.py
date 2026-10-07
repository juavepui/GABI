"""Bounded Kenneth French ZIP responses, without settings or filesystem writes."""

import io
import zipfile

import requests

FF5_URL = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_5_Factors_2x3_CSV.zip"
MOM_URL = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Momentum_Factor_CSV.zip"
HEADERS = {"User-Agent": "GABI (herramienta personal de análisis, uso no comercial)"}


class FrenchFactorSource:
    def __init__(self, *, max_zip_bytes: int = 2_000_000, max_csv_bytes: int = 8_000_000):
        if min(max_zip_bytes, max_csv_bytes) <= 0:
            raise ValueError("Invalid factor response limits")
        self.max_zip_bytes = max_zip_bytes
        self.max_csv_bytes = max_csv_bytes

    def csv(self, url: str) -> str:
        data = bytearray()
        with requests.get(url, timeout=30, headers=HEADERS, stream=True) as response:
            response.raise_for_status()
            for chunk in response.iter_content(chunk_size=64_000):
                if len(data) + len(chunk) > self.max_zip_bytes:
                    raise ValueError("Factor ZIP response exceeds limit")
                data.extend(chunk)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            first = archive.infolist()[0]
            if first.file_size > self.max_csv_bytes:
                raise ValueError("Factor CSV exceeds limit")
            with archive.open(first) as entry:
                csv_data = entry.read(first.file_size + 1)
        if len(csv_data) > self.max_csv_bytes:
            raise ValueError("Factor CSV exceeds limit")
        return csv_data.decode("utf-8", errors="replace")

    def tables(self) -> tuple[str, str]:
        return self.csv(FF5_URL), self.csv(MOM_URL)
