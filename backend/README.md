# Backend Python de GABI

Los paquetes `gabi` y `gabi_api` y sus tests residen aquí. Las dependencias siguen
fijadas en `uv.lock`. Streamlit se conserva en `../app/` durante la transición;
la [API local de F2](../docs/local-api.md) comparte su ranking y filtros.

La [arquitectura vigente](../docs/architecture.md) fija dominio, aplicación,
infraestructura y adaptadores HTTP/CLI. El [plan legacy](../docs/architecture/legacy-migration.md)
describe cómo migrar los módulos actuales sin alterar evidencia publicada.
Comprobar los límites desde aquí con `uv run python ../scripts/check_architecture.py`.

Desde la raíz del repositorio:

```powershell
uv sync --project backend --locked --all-groups
uv run --project backend pytest
uv run --project backend python -m gabi_api.bootstrap
uv run --project backend streamlit run app/streamlit_app.py
```

Desde esta carpeta:

```powershell
uv sync --locked --all-groups
uv run pytest
uv run python -m gabi_api.bootstrap
uv run streamlit run ../app/streamlit_app.py
uv run python -m gabi.frozen_research_ci --check-frozen
uv run python -m gabi.frozen_research_ci --typecheck
uv run python -m gabi.search_ledger --verify
```

Los datos por defecto están en `GABI/data`, independientemente del directorio
de trabajo. `GABI_DATA_DIR` permite elegir otra ruta **absoluta** antes del
arranque. No se copian ni migran los datos al importar el paquete.

La instalación editable se prueba también desde la raíz. Para conservar el
entorno `.venv` anterior y los intérpretes de tareas ya instaladas:

```powershell
.venv/Scripts/python.exe -m pip install --no-deps -e backend
```

Ese comando se ejecuta desde la raíz y supone que las dependencias ya están
instaladas. Las instalaciones nuevas usan `backend/.venv` creado por uv.
Para instalar un wheel fuera del checkout, indicar `GABI_PROJECT_ROOT` absoluto
al repositorio que contiene los documentos y datos históricos.

La compatibilidad de los artefactos y la vuelta a la versión anterior se
documentan en [la entrega F1](../docs/backend-layout-compatibility.md).
