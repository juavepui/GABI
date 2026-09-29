"""Export/check API schemas without opening application data or running a server."""
import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory, gettempdir

from gabi.infrastructure.settings import Settings
from gabi_api.bootstrap import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    with TemporaryDirectory(prefix="gabi-openapi-") as temporary:
        root = Path(temporary).resolve()
        assert root.is_relative_to(Path(gettempdir()).resolve())
        app = create_app(Settings(root))
        rendered = json.dumps(app.openapi(), sort_keys=True, indent=2, ensure_ascii=False) + "\n"
        app.state.market.close()
    if args.check:
        if not args.output.is_file() or args.output.read_text(encoding="utf-8") != rendered:
            raise SystemExit("OpenAPI snapshot changed. Run npm run generate:api in frontend and review the contract.")
        print("OpenAPI snapshot matches the backend")
    else:
        args.output.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
