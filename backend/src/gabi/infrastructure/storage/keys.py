"""Whether each local API key is configured; never their values or paths."""

import os
from pathlib import Path

KEYS = (("fred", "", "fred_api_key.txt"), ("tiingo", "TIINGO_API_KEY", "tiingo_api_key.txt"),
        ("fmp", "FMP_API_KEY", "fmp_api_key.txt"),
        ("nasdaq", "NASDAQ_DATA_LINK_API_KEY", "nasdaq_data_link_api_key.txt"))


def configured_keys(data_dir: Path) -> dict[str, bool]:
    return {name: bool(env and os.environ.get(env)) or (data_dir / filename).is_file()
            for name, env, filename in KEYS}
