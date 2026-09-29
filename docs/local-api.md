# API local de GABI — F2 / #64

La API FastAPI comparte el cálculo y los filtros del Screener con Streamlit.
Es una entrega de consulta para Mercado y estado local del modelo. React llega
en #65; las acciones de actualización y los jobs persistentes, en #66.
Los datos y las fórmulas publicados permanecen en su ubicación y versión.

## Arranque

Desde la raíz del repositorio:

```powershell
uv sync --project backend --locked --all-groups
uv run --project backend python -m gabi_api.bootstrap
```

Escucha en `127.0.0.1:8000`. Este lanzador no acepta opciones ni variables para
abrir una interfaz pública. Documentación interactiva: <http://127.0.0.1:8000/docs>;
contrato generable: <http://127.0.0.1:8000/openapi.json>. CORS permite exclusivamente
`http://localhost:5173` y `http://127.0.0.1:5173`, con GET y sin credenciales.

`GABI_DATA_DIR` permite indicar otra carpeta **absoluta**. Un wheel instalado fuera
del checkout requiere también `GABI_PROJECT_ROOT` absoluto, por la compatibilidad
de rutas F1 de los motores publicados. La CI extrae el wheel y verifica sus imports
y respuestas con una carpeta de datos temporal ausente, fuera del checkout.

Streamlit continúa disponible:

```powershell
uv run --project backend streamlit run app/streamlit_app.py
```

## Contrato v1

| GET | Resultado |
| --- | --- |
| `/api/v1/health` | Salud del proceso; no consulta ni crea datos |
| `/api/v1/model` | Modo local, pesos activos, modelo, evidencia y origen del seguimiento |
| `/api/v1/data/status` | Cobertura/frescura del universo local; reutiliza la caché del ranking |
| `/api/v1/ranking` | Ranking, métricas, filtros/paginación, sectores y procedencia |
| `/api/v1/companies/{symbol}?bars=252` | La misma fila/score calculada sobre todo el universo, más cierres recientes |

Filtros: `search` literal sin regex (hasta 100 caracteres), `sectors` repetible
(hasta 11), `min_market_cap` en **USD**, `golden_cross_only`, `hide_no_data`
(por defecto true), `offset` 0..1000 y `limit` 1..500. Se calcula el ranking de
todo el universo antes de filtrar/paginar para conservar los percentiles por
sector y el orden publicado, incluidos empates. `rank` indica su posición en
ese universo antes del filtro. La ficha conserva ese score: no vuelve a puntuar
la empresa aislada. Los símbolos se normalizan a mayúsculas y punto→guion.
Dos clases con el mismo CIK conservan sus filas y precios separados.

```text
/api/v1/ranking?search=brk&sectors=Financials&min_market_cap=1000000000&limit=20
/api/v1/companies/BRK-B?bars=100
```

Cada métrica contiene `value` y `unit`. Los ausentes y valores no finitos se
serializan como `null`; las respuestas nunca contienen NaN/Infinity. Unidades:
`fraction` (0.09 = 9 %), `percent` (debt/equity de Yahoo ya multiplicado por 100),
`points_0_100` (scores, confianza y percentiles), `USD`, `ratio`, `count`.
Los cierres y medias son USD; `close` y `adj_close` se declaran por separado.
Las fechas de cotización/eventos/filings son ISO y las fechas de descarga,
timestamps. Se conservan identidad, candidatos, confianza y fuente de alias;
no se infiere un CIK acreditado de un ticker sin alias operativo vigente.
Los enlaces de filings expuestos son HTTPS de SEC. La procedencia declara
`full_cached_history`, fuente/caché y `historical_point_in_time=false`: esta
consulta actual no acredita precios o fundamentales históricos point-in-time.

`ready` significa datos cacheados con frescura suficiente según esta política,
no acreditación de su calidad financiera. `empty` significa que faltan universo
o precios/fundamentales; una selección vacía por filtros conserva el estado de
los datos subyacentes. `stale` mantiene resultados y avisos: precios/universo de
más de 7 días, fundamentales de más de 7 o SEC de más de 14 días. Cobertura
incompleta se informa por separado; el score/13 métricas/confianza mantiene las
reglas originales. Errores de lectura dan HTTP 503 con `status="error"`; un cambio
concurrente de inputs da 409 para repetir. Archivo corrupto y archivo ausente
son casos distintos. Los errores 403/404/409/422/500/503 usan la envoltura
`{"status":"error","error":{"code":"…","message":"…"}}`, sin rutas, claves,
SQL ni inputs sensibles en la respuesta.

Investor utiliza siempre los pesos congelados. Una URL `mode=RESEARCH` no puede
cambiar el modo persistido localmente. Solo si este ya es Research se admiten
los cuatro parámetros `value`, `quality`, `momentum`, `risk`: fracciones finitas,
no negativas, con suma 1. No se guardan por consultar. Se etiqueta EXPERIMENTAL
cualquier desviación; coincidencia es FROZEN o LIVE_FORWARD si existen metadatos
de seguimiento. LIVE_FORWARD distingue validación ciega bloqueada con periodos
registrados de la señal débil de Research Lab. Ninguna implica éxito: el contrato
mantiene `independent_advantage_demonstrated=false` y no publica VALIDATED.
Solo se leen id/estado/pesos y existencia de periodos; no se leen precios de
entrada, picks, rankings sellados, retornos ni resultados de reservas ciegas.

## Capas y consultas

- `application/market/ranking.py`: caso de cálculo común, con entradas y motores
  inyectados. `screener.build_screener_table` es la fachada de compatibilidad.
- `domain/market`: filtros, resolución conservadora de alias y unidades.
- `application/market/queries.py` y `application/administration/model.py`:
  consulta de ranking/ficha y política del modelo con puertos explícitos.
- `infrastructure/legacy/market.py`: funciones existentes sin copiar fórmulas.
- `infrastructure/storage/market.py`: SQL de solo lectura, lotes y caché.
- `gabi_api`: traducción HTTP/JSON; únicamente `bootstrap.py` compone adaptadores.

La API abre SQLite con URI `mode=ro` y `query_only=ON`. No inicializa esquemas,
migra tablas, cambia el journal, descarga fuentes ni usa los getters legacy que
ejecutan DDL. Una base/tabla ausente deja ausentes sus datos. SQLite conserva su
coordinación normal de lectores/WAL; las consultas no modifican registros,
configuración ni artefactos. El adaptador Streamlit antiguo conserva sus getters
mientras se migra su administración. Los 18 motores/config congelados y los
artefactos publicados siguen verificables; no se abren holdouts para probar F2.

## Límites y caché

El universo está limitado a 1000 símbolos. Precios se leen por lotes de 16,
columnas explícitas y como máximo 160 000 filas por lote; SPY hasta 10 000.
Se conserva **todo** el histórico cacheado necesario para riesgo y RSI: superar
el presupuesto produce `resource_limit`, nunca un recorte silencioso que cambie
las métricas. La respuesta de precios de una ficha admite 1..1000 barras.
CSV/JSON de configuración y cada estado fundamental tienen límite de 1 MB;
no se recorren, copian ni hashean los aproximadamente 83 GB de `data/`.

La caché del proceso conserva hasta cuatro rankings durante cinco minutos.
Su clave incluye fecha actual (eventos/frescura), pesos, modelo/versionado del
caso de uso, benchmark/configuración, contenido del universo y revisión SQLite.
Filtros/paginación se aplican después sobre la misma base. La revisión usa
`PRAGMA data_version` sobre **una conexión de lectura persistente**, identidad
del fichero y marcas DB/WAL; detecta escrituras legacy y correcciones históricas
aunque no cambie la última fecha. Cerrar/reabrir la API vacía la caché. Una
transacción de lectura mantiene consistente el cálculo por lotes; si cambian
DB/universo durante la consulta, se rechaza ese resultado y se vuelve a intentar.
Ficha y gráfico también comprueban que comparten revisión.

`revision` es un identificador efímero para invalidar esta caché, **no** un hash de
evidencia reproducible ni sustituto de los fingerprints publicados. El TTL no
acredita integridad. F4 añadirá la revisión transaccional de los comandos/jobs;
la conexión persistente cubre entretanto los commits de los escritores legacy.
Un candado local serializa el cálculo frío y evita duplicarlo en peticiones
simultáneas; no se arrancan workers desde GET. Es un cálculo de pantalla, no un
backtest, y su primer acceso aún puede tardar segundos con históricos grandes.

## Verificación y medición

Los tests usan bases sintéticas temporales: paridad contra una referencia de
**16 empresas × 86 columnas**, obtenida del commit pre-F2
`cd433a2e466df32d38aaaf3a5d1877857b0ce67e`; datos incompletos, alias ambiguos y dos
clases del mismo emisor. Se prohíben red, escrituras de archivos, SQL mutable y
lectura de columnas ciegas; se comprueban contratos, filtros, límites,
Investor/Research, errores, CORS, invalidez de históricos corregidos y WAL.
Las pruebas de arranque Streamlit, arquitectura, tipos y hashes siguen en CI.

Medición reproducible, solo con una base temporal sintética:

```powershell
uv run --project backend python scripts/measure_api.py --output docs/api-f2-measurement.json
```

Resultado en Windows/Python 3.13.7, semilla 64, **504 empresas, 1250 sesiones,
628 755 filas de precios**; filas y todas las métricas iguales:

| Camino | Tiempo | Pico de asignaciones Python | SELECT | Filas devueltas por adaptador nuevo |
| --- | ---: | ---: | ---: | ---: |
| Fachada Streamlit, I/O legacy | 20.1064 s | 307.450 MiB | 5 | — |
| API sin ranking en caché | 21.0030 s | 12.678 MiB | 103 | 630 063 |
| API con ranking en caché | 0.0476 s | 0.968 MiB | 3 | 18 |

[Registro completo](api-f2-measurement.json), incluidos totales SQL. Es una medida
del caso de uso con `tracemalloc`, que añade coste: no incluye serialización HTTP,
memoria nativa ni RSS total; no controla la caché de disco del sistema operativo.
La lectura por lotes aumenta las consultas y reduce las asignaciones retenidas;
el cálculo frío conserva su coste financiero. No son límites de RAM ni garantías
de latencia sobre la base real. No se consultó esta para obtener las cifras.
