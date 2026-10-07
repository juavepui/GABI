# F7.4: inventario anual y reglas de cobertura histórica

El inventario anual 2008–2026 usa el caso de uso de aplicación, un puerto de
lectura y un escritor CSV. `gabi_cli research historical-data-audit` compone sus
entradas SQLite/CSV y publica únicamente al ejecutar el comando explícito.
SQLite se abre existente, con `mode=ro` y `query_only`; el contexto cierra la
conexión. La consulta no descarga ni inicializa tablas, pesos o cachés.

Las reglas de cobertura y los 13 ingredientes usan implementaciones únicas
de dominio para SEC, indicadores y riesgo. Se conservan exclusión de filings
futuros, ajustes nominales por splits posteriores (incluidos cero y ausencia),
frescura de 460/10 días, identidad candidata frente a acreditada, fuentes,
orden de columnas y fecha de corte basada en el último precio ajustado de SPY.
El comando trimestral usa [las mismas reglas de dominio](f7-quarterly-coverage.md)
con ajustes y alineación fiscal explícitos, sin cambiar globales.

Las lecturas de precios conservan el historial disponible hasta el corte para
no cambiar el drawdown. Su límite es 25.000 filas por símbolo; hechos, aliases
y snapshots admiten 100.000 filas por lectura, archivos 32 MB, símbolos 1.000
y lotes 50. Se rechaza el exceso antes de publicar; nunca se calcula sobre una
serie truncada. Los conteos anuales se consultan por lotes con año y símbolos
explícitos. Los hechos y precios para métricas se consumen un símbolo a la vez
dentro de cada lote, sin cargar toda la base. No hay caché: cada ejecución relee los inputs; el
detalle trimestral previo se valida contra la membresía anual y debe regenerarse
si sus datos cambian, como exigía el comando original.

La fachada `historical_data_audit.py` conserva solo `connect_readonly`, todavía
usado por la auditoría de precios plana. Se retirará con ese consumidor. El
adaptador SEC actual ya usa la conexión de infraestructura. El inventario de
excepciones pierde los imports antiguos de cálculo, configuración y calendario;
la fachada no autoriza funcionalidades nuevas.

Las pruebas comparan el informe completo y bytes CSV frente a la fuente original
capturada, con SQLite y CSV sintéticos temporales. Incluyen errores por falta
de benchmark, cambio de miembros, límites, lecturas sin escritura y cierre de
conexión. Ningún artefacto publicado se regenera ni se consultan reservas.

Medición reproducible: `.venv/Scripts/python.exe scripts/measure_f7_historical_data_audit.py`.
Se registra por separado la paridad del informe y el coste de lectura/cálculo;
el pico de `tracemalloc` mide asignaciones Python, no RSS.

Resultado en Windows/Python 3.13, mismo caché sintético de 19 años y 36 columnas,
una pasada de calentamiento y tres repeticiones: medianas 3,5556 s original y
3,4487 s migrado; picos de asignaciones Python 1,508 y 1,479 MiB. Todas las
columnas y textos CSV coinciden. La medida no acredita una mejora general de
velocidad, ni representa el inventario completo de los datos locales. El arnés
cierra explícitamente también la conexión de referencia al terminar cada pasada.
