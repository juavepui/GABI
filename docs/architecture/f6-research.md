# F6 · Investigación y distribución local (#68)

F6 se entrega por recorridos verificables. Este primer tramo sustituye la portada
vacía de Investigación por el catálogo **ya publicado** en
`docs/search-ledger/ledger.json`: 34 entradas de la convención histórica,
observaciones adicionales, diagnósticos, fallos y límites. No calcula ni abre
ninguna reserva; el registro publicado declara expresamente que su recuento no es
exhaustivo ni controla el error global de todas las búsquedas. La #60 permanece
pendiente de evidencia independiente.

La API lee solo el fichero explícito, con tope de 2 MB, y almacena su JSON en
memoria hasta que cambian tamaño o mtime. La CI verifica el registro frente a
sus fuentes publicadas. Las respuestas seleccionan campos de metadatos;
`configuration` y cualquier campo adicional quedan fuera del contrato. No se
consulta `gabi.db`, resultados operativos, periodos ciegos ni los datasets
reservados de #43/#44. Una ausencia o estructura inesperada devuelve 503.

El Ranking histórico reconstruye por job una fecha del S&P 500 en el intervalo
ya observado 2010-01-01 a 2025-07-02. La validación de fechas está en el
backend: ni la UI ni una llamada directa pueden abrir el periodo pre-2010 de
#43 o fechas prospectivas. El worker usa el motor legacy intacto y conserva
todas las filas en un artefacto JSON con hash; la pantalla presenta las primeras
100 y permite descargar el resultado completo. Es exploración retrospectiva,
no validación fuera de muestra. Los backtests V1/V2 de esta página siguen en
Streamlit hasta migrar sus parámetros, costes y registro de ensayos.
El job exploratorio `backtest` que ya existía en Administración también queda
limitado a la misma ventana observada. La API verifica la fecha tanto al
encolar como al leer artefactos de jobs antiguos: una URL directa no puede
eludir la reserva de #43. El universo del motor sigue siendo S&P 500; no se
ofrece el conjunto reservado fuera del índice de #44.
Medición de la serialización, no del cálculo histórico ni de SQLite:
`python scripts/measure_f6_historical.py` en Windows/Python 3.13.7, fixture
sintética de 500 empresas y 62 columnas, 999.398 bytes JSON, 0,3844 s y
3,454 MiB de pico de asignaciones Python medido con `tracemalloc`. El resultado
queda bajo el límite de 10 MB del worker en esta fixture; no se extrapola a
los datos locales ni se atribuye una mejora de rendimiento al cambio de UI.

El build de Vite puede servirse desde FastAPI bajo `127.0.0.1:8000`; el mismo
origen sirve `/api/v1`, `/assets` y las rutas de React. `gabi_cli serve` inicia
API y worker, los detiene juntos y exige un build presente. El modo de desarrollo
con Vite continúa disponible. No se retira Streamlit mientras falten sustitutos
de los cinco recorridos de Investigación y la pestaña de backtest SMA heredada.

| Recorrido F0 | Estado F6 | Paso pendiente para equivalencia |
| --- | --- | --- |
| Ranking histórico | Ranking por fecha en React y job; backtests en Streamlit | Backtests V1/V2 como jobs con costes y registro íntegros. |
| Research Lab | Catálogo público en React; operaciones antiguas en Streamlit | Ensayos operativos, artefactos, estadísticas y exportaciones con reglas de reserva. |
| Factor Lab | Streamlit | Análisis por factor y ventanas mediante jobs con procedencia. |
| Blind Forward Validation | Streamlit | Alta, rebalanceos, sellos y revelación protegidos por API y preregistro. |
| Portfolio Lab | Streamlit | Construcciones y riesgo mediante jobs con costes idénticos. |

Antes de cerrar #68 se comprobarán los 17 recorridos del inventario F0, la
paridad de cálculos y persistencia, la recuperación local y los límites de
memoria/tiempo. Solo entonces se retirarán consumidores y dependencias
Streamlit sin tocar los motores y artefactos publicados.
