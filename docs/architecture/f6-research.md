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

El build de Vite puede servirse desde FastAPI bajo `127.0.0.1:8000`; el mismo
origen sirve `/api/v1`, `/assets` y las rutas de React. `gabi_cli serve` inicia
API y worker, los detiene juntos y exige un build presente. El modo de desarrollo
con Vite continúa disponible. No se retira Streamlit mientras falten sustitutos
de los cinco recorridos de Investigación y la pestaña de backtest SMA heredada.

| Recorrido F0 | Estado F6 | Paso pendiente para equivalencia |
| --- | --- | --- |
| Ranking histórico | Streamlit | Ranking por fecha, cobertura y backtests V1/V2 como jobs con resultados íntegros. |
| Research Lab | Catálogo público en React; operaciones antiguas en Streamlit | Ensayos operativos, artefactos, estadísticas y exportaciones con reglas de reserva. |
| Factor Lab | Streamlit | Análisis por factor y ventanas mediante jobs con procedencia. |
| Blind Forward Validation | Streamlit | Alta, rebalanceos, sellos y revelación protegidos por API y preregistro. |
| Portfolio Lab | Streamlit | Construcciones y riesgo mediante jobs con costes idénticos. |

Antes de cerrar #68 se comprobarán los 17 recorridos del inventario F0, la
paridad de cálculos y persistencia, la recuperación local y los límites de
memoria/tiempo. Solo entonces se retirarán consumidores y dependencias
Streamlit sin tocar los motores y artefactos publicados.
