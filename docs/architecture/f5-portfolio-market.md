# F5 · Cartera y Mercado (#67)

Inventario de sustitución de los ocho recorridos Streamlit de esta fase. React
usa la API local; los cálculos y decisiones financieras siguen en Python.
Streamlit permanece operativo durante la transición a F6.

| Recorrido | Sustitución local | Compatibilidad y límite |
| --- | --- | --- |
| Mi cartera | `/cartera`, plan Top-N y aportación de capital | Selección y reparto en `domain/portfolio/selection.py`; Top-20 con pesos congelados, otros N experimentales. Capital EUR y precio USD separados; no se inventa un tipo de cambio ni se envían órdenes. |
| Comparar empresas | `/mercado/comparar` | Un solo ranking backend para 2–5 símbolos, con unidades, nulls y procedencia de la ficha. |
| Diario de inversión | `/cartera/diario` | Misma tabla `investment_journal` en `gabi.db`; lectura, tesis, revisión y borrado explícitos. Valor esperado compartido en dominio. |
| Panel Macro | `/mercado/macro` | Últimos puntos de las series FRED cacheadas. GET no inicia descargas; el refresco local se encola desde Administración. |
| Signal Monitor | `/mercado/senales` | Snapshots y eventos en las tablas históricas; comparación de ranking explícita e idempotente. Earnings de candidatas en GET; comparación 10-K/10-Q sobre `edgar_facts` cacheados por job y guardado explícito de comparaciones/eventos. No se interpreta un evento como orden. |
| Aprender | `/cartera/aprender` y ayuda contextual en las fichas | Guía breve orientada a los flujos actuales. El tutorial extenso permanece como material de referencia en Streamlit hasta decidir su edición en F6; no contiene cálculos nuevos para duplicar. |
| Decisiones | `/cartera/decisiones` | Misma `Policy` experimental, optimizador y tabla `decision_runs`; cálculo por job, guardado posterior de artefacto verificado, progreso ponderado y SPY. No equivale al Top-20 congelado ni acredita ventaja. |
| Carteras simuladas | `/cartera/simuladas` | Misma contabilidad de cierres, comisiones, spread y FX, y tablas `sim_portfolios`/`sim_trades`; alta, operación, deshacer, curva y comparación entre carteras. Historial largo y comparación por worker. |

La pestaña de cruce SMA de la antigua página de carteras es un **backtest de
investigación**, no contabilidad de una cartera manual. Permanece accesible en
Streamlit y su traslado corresponde a F6; no se reetiqueta como estrategia
validada. La eliminación de Streamlit exige revisar este contenido educativo y
el backtest antes de retirar sus páginas.

## Datos, efectos e invalidación

Las consultas GET usan SQLite en modo de solo lectura, ventanas de filas y
ninguna descarga. La lectura de decisiones usa lotes de 25 símbolos y como
máximo 756 sesiones por símbolo; el progreso de un plan admite 30 posiciones y
5.000 sesiones por símbolo. Simulaciones admiten 500 operaciones y 30 símbolos;
el cálculo HTTP se deriva a job cuando supera tres años, diez símbolos o cien
operaciones. Filings admite 30 candidatas y 50.000 hechos SEC por símbolo en
un job. Los límites excedidos producen un error explícito, no un resultado
silenciosamente truncado.

El ranking comparte la revisión de caché de F2. Una escritura a `gabi.db` por
Streamlit, API o worker invalida el ranking de proceso; la cola en
`gabi_jobs.db` no lo invalida. Los planes y snapshots guardados son fotos
fechadas y se releen por ID; los precios de progreso se consultan al abrir el
plan y pueden cambiar tras un refresco de datos. El resultado de un job se lee
con su SHA-256 antes de guardar planes o comparaciones SEC. Estas revisiones
de caché no son hashes probatorios de una estrategia.

## Equivalencia y medición

Las fixtures de `backend/tests/` prueban tablas históricas, ausencia de efectos
en GET, selección, importes, costes, FX, retornos y progreso ponderado. Los
recorridos Playwright cubren cartera, diario, comparación, macro, snapshots,
filings, simulaciones y decisiones. Se verifican además OpenAPI/tipos, límites
de arquitectura y hashes congelados. Ninguna prueba abre `data/gabi.db`.

Medición reproducible: `python scripts/measure_f5.py --companies 100 --sessions 500`
en Windows/Python 3.13.7, fixture sintética de 104 símbolos (incluidos cuatro
casos especiales), 51.005 filas ajustadas. Lectura legacy: 1,2197 s,
24,958 MiB pico de asignaciones Python, 1 SELECT. Lectura F5 por lotes:
2,2411 s, 6,943 MiB, 6 SELECT; las 51.005 cotizaciones ajustadas coinciden.
La nueva lectura ahorra memoria Python en esa fixture a costa de más tiempo de
CPU/SQL. `tracemalloc` no mide toda la RAM nativa y la caché del sistema
operativo no se controló. No extrapolar estos números a los 83 GB locales.
