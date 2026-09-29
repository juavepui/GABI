"""Loopback test API. No real configuration, credentials, database or network sources."""
import sys
from pathlib import Path
from tempfile import TemporaryDirectory, gettempdir

import uvicorn

from gabi.infrastructure.settings import Settings
from gabi_api.bootstrap import create_app

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend" / "tests"))
from market_fixture import TODAY, seed_fixture  # noqa: E402


def main():
    with TemporaryDirectory(prefix="gabi-react-e2e-") as directory:
        root = Path(directory).resolve()
        assert root.is_relative_to(Path(gettempdir()).resolve())
        seed_fixture(root)
        app = create_app(Settings(root), today=lambda: TODAY)
        uvicorn.run(app, host="127.0.0.1", port=8001, log_level="warning")


if __name__ == "__main__":
    main()
