"""Serve the built local React client from the API's loopback origin."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from starlette.exceptions import HTTPException


def mount_frontend(app: FastAPI, dist: Path) -> None:
    root = dist.resolve()
    index = root / "index.html"
    if not index.is_file():
        raise ValueError("Build React inexistente; ejecuta npm --prefix frontend run build.")

    @app.get("/{client_path:path}", include_in_schema=False)
    def frontend(client_path: str) -> FileResponse:
        if client_path == "api" or client_path.startswith("api/"):
            raise HTTPException(status_code=404)
        target = (root / client_path).resolve()
        if not target.is_relative_to(root):
            raise HTTPException(status_code=404)
        if target.is_file():
            return FileResponse(target)
        if "." in Path(client_path).name:
            raise HTTPException(status_code=404)
        return FileResponse(index, headers={"Cache-Control": "no-store"})
