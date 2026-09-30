# Frontend local de GABI — F6 en curso / #68

React + TypeScript + Vite, React Router, shadcn/ui y TanStack Query.
El Screener y la ficha consultan el backend FastAPI. Los cálculos financieros,
filtros y ordenación se ejecutan en Python. Los aproximadamente 83 GB de data/
permanecen en la carpeta compartida y no se copian al frontend.

## Arranque local

Requisitos: Node **22.13+ (serie 22) o 24+** y el entorno Python del backend instalado.
Para la interfaz React y el worker bajo un solo origen, desde la raíz:

```powershell
uv sync --project backend --locked --all-groups
npm --prefix frontend ci
npm --prefix frontend run build
uv run --project backend python -m gabi_cli serve
```

Abre **http://127.0.0.1:8000**. `serve` escucha solo en loopback, atiende
React y `/api/v1` en ese origen e inicia el worker. Ctrl+C detiene ambos.
El build debe repetirse al actualizar el frontend. Los datos permanecen en
`data/`; el build no los copia. El catálogo de Investigación se lee de los
metadatos publicados del checkout. Streamlit continúa disponible para los
recorridos de investigación aún no migrados.

Para desarrollo con recarga de Vite, usa dos terminales. Primera:

```powershell
uv sync --project backend --locked --all-groups
uv run --project backend python -m gabi_api.bootstrap
```

En otra terminal:

```powershell
cd frontend
npm ci
npm run dev
```

Abre **http://127.0.0.1:5173**. La API escucha solo en
**http://127.0.0.1:8000**. Vite y su preview reenvían `/api` al backend;
no hace falta habilitar CORS. Para otra dirección local, configura
`GABI_API_TARGET` antes de arrancar Vite. El frontend no acepta una carpeta
de datos: ese ajuste pertenece al [backend](../docs/local-api.md).

Para procesar solicitudes desde Administración, arranca un **tercer proceso**:

```powershell
uv run --project backend python -m gabi_cli worker
```

El worker conserva la cola en `data/gabi_jobs.db` y continúa después de cerrar
el navegador. Puedes instalar las tareas locales mediante
`scripts/programar_tareas.ps1` si quieres que arranque al iniciar sesión y que
el refresco diario/Tiingo se encolen sin abrir la app. El script no se ejecuta
al instalar GABI; las tareas ya registradas se actualizan solo al ejecutarlo.

Si ya utilizas el entorno raíz de Windows:

```powershell
.venv/Scripts/python.exe -m gabi_api.bootstrap
```

Para comprobar el build local, usa `npm run build` y `npm run preview`.
Los servidores se detienen con Ctrl+C. La retirada de Streamlit espera la
equivalencia de los cinco recorridos F6.

## Flujos disponibles

Mercado incluye búsqueda por nombre/símbolo, sectores, capitalización mínima en
USD, cruce dorado, empresas sin datos, ordenación y páginas. La URL conserva
filtros, orden y página al recargar y al volver de una ficha. La ficha muestra
score, cobertura, métricas, precios ajustados sin rellenar ausencias, documentos
SEC, identidad y procedencia. El gráfico tiene una tabla accesible.

`—` significa dato ausente, no cero. Cobertura/confianza se refiere a métricas
disponibles, no a probabilidad de éxito. Se distinguen caché vacía, selección
vacía, errores y datos obsoletos. Un modelo congelado o en seguimiento **no**
acredita ventaja frente a SPY.

Mercado añade comparación entre empresas, Panel Macro y Signal Monitor con
snapshots, filings SEC cacheados y calendario de resultados. Cartera incorpora
plan objetivo, diario, ayuda contextual, decisiones experimentales y carteras
simuladas. [Cobertura y límites de F5](../docs/architecture/f5-portfolio-market.md).
Investigación muestra el registro de búsquedas publicadas, incluidos ensayos
fallidos y límites de evidencia. El resto de sus recorridos sigue en Streamlit.
[Cobertura y pasos pendientes de F6](../docs/architecture/f6-research.md).
Administración permite encolar refrescos incrementales, hasta diez símbolos,
auditoría de cobertura y un backtest exploratorio de hasta un año. Muestra el
estado persistente, cancelación cooperativa y resultados verificados por hash.
El mantenimiento #43/#44 solo lo encola el programador; nunca publica resultados
ciegos en el cliente. Las claves se configuran localmente y el cliente solo ve
si están presentes. Los pesos por defecto se editan en Administración cuando el
modo local ya es Research; Investor los mantiene bloqueados. El cambio de modo
sigue temporalmente en Streamlit.
Para esos flujos, conserva esta vía de vuelta desde la raíz:

```powershell
uv run --project backend streamlit run app/streamlit_app.py
# O, con el entorno raíz de Windows:
.venv/Scripts/python.exe -m streamlit run app/streamlit_app.py
```

## Contrato, arquitectura y comprobaciones

El único transporte HTTP está en `src/shared/api/client.ts`.
`openapi.json` se exporta de una app con carpeta temporal; el generador produce
`src/shared/api/generated/`. No se mantienen esquemas financieros manuales.
TanStack Query cancela consultas abandonadas, comparte solicitudes de la misma
clave y conserva la caché 5 minutos (frescura del cliente: 30 segundos). El
backend determina la frescura de los datos. El gráfico se descarga al abrir
una ficha. El formulario mantiene un borrador local; solo envía al aplicarlo.

```powershell
cd frontend
npm run generate:api       # Solo cuando cambia el contrato Python
npm run check:api          # Falla si esquema o tipos versionados difieren
npm run lint
npm run format:check
npm run test:architecture
npm run typecheck
npm test
npm run build
npx playwright install chromium
npm run test:e2e
```

Los scripts localizan `backend/.venv` o `.venv` de la raíz. Para otro entorno,
define `GABI_PYTHON` con la ruta absoluta del ejecutable.

Playwright arranca una **API de pruebas en 8001** con SQLite, pesos y universo
sintéticos en una carpeta temporal y el build en 5173. Rechaza servidores ya
abiertos en esos puertos: detén tu Vite antes de ejecutar los tests. No utiliza
`data/gabi.db`, claves, resultados ciegos ni fuentes externas. Las pruebas de
flujo comparan valores/selección con la API real; otras inyectan únicamente
estados de transporte para probar errores, carga y obsolescencia. Chromium y
axe comprueban teclado y accesibilidad en escritorio y 390 px.

La CI ejecuta todo lo anterior. El informe de navegador incluye capturas,
trazas en fallos y una medición acotada de navegación fría/caliente, peticiones
y heap JavaScript del navegador instrumentado con axe. No mide el consumo total
del equipo ni del conjunto local de 83 GB.

Medición local F3 (2026-09-29, Node 22.19, Chromium, build de producción;
16 empresas y 320 sesiones en SQLite temporal): primera navegación **997 ms**;
vuelta desde ficha **83 ms**. Hubo **1 petición de ranking y 1 de ficha**;
la vuelta al listado reutilizó su caché sin otra petición. Heap JS observado:
5.107.072 bytes al cargar y 25.396.088 después de la ficha y los análisis axe.
Estas dos cifras incluyen distinta instrumentación y no son un antes/después
de consumo de la aplicación. La CI adjunta su propia medición en
`bounded-navigation.json`; los tiempos no son umbrales de aceptación.

Respetar [la arquitectura](../docs/architecture.md), sus guardas y
[AGENTS.md](../AGENTS.md). App compone las features por sus índices públicos;
cada feature usa su código y shared. No añadir cálculos de scoring al navegador.

Todas las dependencias y el generador están fijados en el lockfile. El override
`js-yaml@4.3.2` corrige la dependencia transitiva del parser OpenAPI; retirar el
override cuando el generador incorpore esa versión.
