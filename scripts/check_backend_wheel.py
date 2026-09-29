"""Verify the built wheel, without relying on editable imports or real data."""
import os
import subprocess
import sys
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory, gettempdir

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    wheel = Path(sys.argv[1]).resolve()
    with TemporaryDirectory(prefix="gabi-wheel-") as temporary:
        installed = Path(temporary).resolve()
        assert installed.is_relative_to(Path(gettempdir()).resolve())
        assert installed.name.startswith("gabi-wheel-")
        with zipfile.ZipFile(wheel) as archive:
            for name in archive.namelist():
                if not (installed / name).resolve().is_relative_to(installed):
                    raise ValueError("Unsafe wheel member")
            archive.extractall(installed)
        data = installed / "empty-data"
        script = """
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import gabi
import gabi_api
from gabi_api.bootstrap import create_app
from fastapi.testclient import TestClient
assert Path(gabi.__file__).is_relative_to(Path(sys.argv[1]))
assert Path(gabi_api.__file__).is_relative_to(Path(sys.argv[1]))
with TestClient(create_app()) as client:
    assert client.get('/api/v1/health').status_code == 200
    assert client.get('/api/v1/ranking').json()['data']['status'] == 'empty'
assert not Path(sys.argv[2]).exists()
print('Wheel imports and empty-cache HTTP contract OK outside the checkout')
"""
        subprocess.run([sys.executable, "-I", "-c", script, str(installed), str(data)], cwd=installed,
                       env={**os.environ, "GABI_PROJECT_ROOT": str(ROOT), "GABI_DATA_DIR": str(data)}, check=True)


if __name__ == "__main__":
    main()
