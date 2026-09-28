# Requisitos locales reales de GABI

## ¿Cuánto ocupa data y qué hay que conservar?

### Takeaway

La afirmación del usuario es correcta: la primera medición da **89.288.750.430 bytes = 89,29 GB decimales = 83,1566 GiB**, redondeado a 83,2 en Windows, repartidos en 24.738 archivos. La base activa ocupa **12.333.223.936 bytes = 12,33 GB = 11,49 GiB**; gran parte del resto son fuentes históricas y snapshots de investigación, por lo que no es correcto tratarlos automáticamente como caché prescindible. La medición persistida unos minutos después añade únicamente dos archivos auxiliares de SQLite WAL: 32.768 bytes y dos archivos, sin cambios en la base principal. [Inventario medido](C:/Users/jvela/source/GABI/research_notes/Viabilidad%20gratuita%20de%20GABI/medicion_data.json)

### Cited Findings

- Método: recorrido `os.walk(data)` sumando `Path.stat().st_size`, sin leer contenidos de datos, sin descargas y sin errores. Es tamaño lógico de archivos, **no** espacio físico reservado en clústeres, deduplicación, compresión o bloques del sistema de archivos. La medición persistida fue el 28-09-2026 a las 12:58:43 UTC: 89.288.783.198 bytes, 89,288783198 GB, 83,156659452 GiB, 24.740 archivos. [Medición](C:/Users/jvela/source/GABI/research_notes/Viabilidad%20gratuita%20de%20GABI/medicion_data.json)
- Desglose principal antes de los auxiliares WAL:

  | Ubicación | Bytes | GB decimales | Archivos |
  |---|---:|---:|---:|
  | `history_refresh` | 54.481.302.844 | 54,48 | 23.468 |
  | Archivos de raíz | 15.866.002.738 | 15,87 | 16 |
  | `revalidation_2011_2025` | 13.663.631.456 | 13,66 | 188 |
  | `historical_validation_2010_2015` | 2.811.367.226 | 2,81 | 26 |
  | `full_universe_audit` | 873.619.421 | 0,87 | 41 |
  | `overfitting_audit` | 844.423.342 | 0,84 | 40 |
  | `kaggle` | 694.458.541 | 0,69 | 4 |
  | `smallmid_test` | 50.083.493 | 0,050 | 823 |

  Las demás carpetas suman menos de 5 MB. [Inventario, profundidad 1](C:/Users/jvela/source/GABI/research_notes/Viabilidad%20gratuita%20de%20GABI/medicion_data.json)
- `history_refresh/validation_1996_2015` concentra **50.737.197.310 bytes / 50,74 GB**. Dentro: instancias XML 20,23 GB; companyfacts JSON 11,33 GB; informes anuales HTML 9,83 GB; archivos en su raíz 7,93 GB; submissions de identidad 1,15 GB. [Inventario, profundidades 2 y 3](C:/Users/jvela/source/GABI/research_notes/Viabilidad%20gratuita%20de%20GABI/medicion_data.json)
- Archivos grandes: `gabi.db` 12,33 GB; cuatro snapshots en `revalidation_2011_2025` de 3,47 / 3,47 / 3,30 / 3,30 GB; `historical_validation_2010_2015/snapshot.db` 2,80 GB; `gabi.db.before-identity.bak` 2,67 GB; `history_refresh/validation_1996_2015/before_validation.db` 2,43 GB; dos backups de `history_refresh` de 1,63 y 0,85 GB; `rotation_experiment_work.db` 0,85 GB. [40 archivos mayores](C:/Users/jvela/source/GABI/research_notes/Viabilidad%20gratuita%20de%20GABI/medicion_data.json)
- Todas las `.db` suman 36.130.480.128 bytes. Restando la activa y añadiendo `.bak`, las demás bases/snapshots/backups suman **26.468.478.976 bytes / 26,47 GB**. Esta es una clasificación por tipo de archivo, no una autorización para eliminarlos. [Inventario medido y lista de archivos](C:/Users/jvela/source/GABI/research_notes/Viabilidad%20gratuita%20de%20GABI/medicion_data.json)
- La app ubica `data` junto al código y usa `data/gabi.db`; no hay configuración de ruta mediante variable de entorno en `config.py`. `weights.json`, claves de datos y modo de app también se guardan en disco. [config.py](C:/Users/jvela/source/GABI/src/gabi/config.py:6), [app_mode.py](C:/Users/jvela/source/GABI/src/gabi/app_mode.py:60)
- La app escribe, además de caché, información que no debe perderse: diario de inversión, carteras simuladas, decisiones, experimentos y pruebas ciegas, entre otras tablas. [journal.py](C:/Users/jvela/source/GABI/src/gabi/journal.py:62), [sim_portfolios.py](C:/Users/jvela/source/GABI/src/gabi/sim_portfolios.py:92), [decision_engine.py](C:/Users/jvela/source/GABI/src/gabi/decision_engine.py:320), [blind_validation.py](C:/Users/jvela/source/GABI/src/gabi/blind_validation.py:324)
- Los snapshots son inputs reales de investigación. Por ejemplo `cross_section_test` redirige la base a un `snapshot.db` de revalidación; `full_universe_audit` verifica hashes e impide mezclar inputs modificados. La UI Salud de Datos también lee cobertura histórica desde `history_refresh/validation_1996_2015/coverage/quarterly.csv`. [cross_section_test.py](C:/Users/jvela/source/GABI/src/gabi/cross_section_test.py:95), [full_universe_audit.py](C:/Users/jvela/source/GABI/src/gabi/full_universe_audit.py:42), [Salud de Datos](C:/Users/jvela/source/GABI/app/pages/15_Salud_Datos.py:56)
- Se consultaron únicamente PRAGMA mediante `sqlite3.connect('file:data/gabi.db?mode=ro', uri=True)`: `page_size=4096`, `page_count=3011041`, `freelist_count=0`, `journal_mode=wal`, `cache_size=-2000`, `temp_store=0`. La multiplicación páginas × tamaño reproduce exactamente los 12.333.223.936 bytes. No se ejecutó `VACUUM`, `COUNT(*)` masivo ni consultas de tablas de datos. SQLite creó auxiliares `gabi.db-wal` de 0 bytes y `gabi.db-shm` de 32.768 bytes al abrir la base WAL en lectura; se dejaron intactos. La app activa WAL en cada conexión y usa timeout de 30 segundos. [Implementación SQLite](C:/Users/jvela/source/GABI/src/gabi/storage.py:42), [Auxiliares en medición final](C:/Users/jvela/source/GABI/research_notes/Viabilidad%20gratuita%20de%20GABI/medicion_data.json)

### Inferences

- Una instalación básica centrada en el screener podría requerir bastante menos de 89,29 GB, pero determinar un subconjunto completo exige definir el alcance de investigación y auditar rutas dependientes. **No debe reducirse silenciosamente el alcance solicitado**: para trasladar GABI y toda su historia/evidencia tal como está, presupuestar los 89,29 GB más crecimiento, backups, WAL, temporales, sistema y dependencias.
- `freelist_count=0` no muestra páginas libres completas recuperables. No justifica prometer que compactar resolverá el almacenamiento; tampoco mide fragmentación interna ni duplicidad semántica.
- Si se dispone de 150 GB de volumen de datos, el inventario deja aproximadamente 60,71 GB nominales antes de overhead, crecimiento y backups. Una nueva copia de la base actual añadiría aproximadamente 12,33 GB; cuatro snapshots nuevos de tamaño actual añadirían aproximadamente 49,33 GB. Son cálculos de capacidad con el tamaño presente, no previsiones de crecimiento. Conservar margen y limitar nuevos trabajos es necesario.

### Gaps

- No se ha medido crecimiento diario/mensual ni capacidad máxima histórica futura. No hay garantía de que un disco fijo gratuito sea suficiente indefinidamente.
- No se ha medido tamaño físico asignado ni realizado un mapa exhaustivo de dependencias para un despliegue reducido. No se ha eliminado, compactado ni alterado ningún dato de aplicación.

## ¿Qué jobs existen y qué almacenamiento/concurrencia requieren?

### Takeaway

GABI ya dispone de jobs en CLI; una VM persistente puede ejecutarlos junto a Streamlit mediante cron/systemd después de adaptar el programador Windows. El mantenimiento diario normal no copia toda la base, pero ciertos jobs históricos y auditorías sí crean backups/snapshots completos, y las descargas Tiingo pueden durar horas o días. [periodic_tasks.py](C:/Users/jvela/source/GABI/src/gabi/periodic_tasks.py:164), [programar_tareas.ps1](C:/Users/jvela/source/GABI/scripts/programar_tareas.ps1:8), [history_refresh.py](C:/Users/jvela/source/GABI/src/gabi/history_refresh.py:118)

### Cited Findings

- `python -m gabi.periodic_tasks --run`: refresca composición del universo, Yahoo precios/fundamentales, SEC, benchmarks SPY/RSP; registra rebalanceos vencidos si integridad y precios frescos lo permiten; ejecuta el paso final #44 tras congelación; escribe log en `data/periodic_tasks/log.jsonl`. [periodic_tasks.py](C:/Users/jvela/source/GABI/src/gabi/periodic_tasks.py:133), [screener.py](C:/Users/jvela/source/GABI/src/gabi/screener.py:34), [periodic_tasks.run](C:/Users/jvela/source/GABI/src/gabi/periodic_tasks.py:164)
- `python -m gabi.periodic_tasks --tiingo`: lee cola `data/smallmid_test/tiingo_symbols.txt`, usa lock de archivo, descarga JSON faltantes, importa precios en SQLite y deja marca de fin cuando procede. Los archivos permiten reanudar; el cupo de la fuente sigue siendo independiente del alojamiento. [periodic_tasks.resume_tiingo](C:/Users/jvela/source/GABI/src/gabi/periodic_tasks.py:175), [historical_tiingo.fetch](C:/Users/jvela/source/GABI/src/gabi/historical_tiingo.py:75)
- Tiingo se pacea a 80 segundos por solicitud; el código espera 15 minutos por 429, hasta unos tres horas antes de detenerse, y reanuda con archivos cacheados. Una VM que no duerme admite este proceso. Los límites mencionados son lo que contempla el código; esta revisión local no verifica las condiciones actuales del proveedor de datos. [historical_tiingo.py](C:/Users/jvela/source/GABI/src/gabi/historical_tiingo.py:30), [reintentos y parada](C:/Users/jvela/source/GABI/src/gabi/historical_tiingo.py:87)
- El `.ps1` propone `--run` de martes a sábado a las 23:30 y `--tiingo` con primer lanzamiento 02-10-2026 10:00 y repetición de 30 días, límite de ejecución 3 días. **El código no demuestra que estas tareas estén registradas en el equipo**; no se consultó Task Scheduler. La repetición de 30 días no garantiza el día 2 de cada mes pese al comentario del script. [programar_tareas.ps1](C:/Users/jvela/source/GABI/scripts/programar_tareas.ps1:8)
- La UI permite actualizar datos y ampliar precios por demanda. `ensure_decision_prices` descarga lotes de 40 símbolos y `ensure_price_history_asof` puede completar historia faltante. Yahoo fundamentales/splits usan hasta 6 threads; SEC hasta 4. [data_fetch.py](C:/Users/jvela/source/GABI/src/gabi/data_fetch.py:110), [precios por demanda](C:/Users/jvela/source/GABI/src/gabi/data_fetch.py:172), [pool Yahoo](C:/Users/jvela/source/GABI/src/gabi/data_fetch.py:231), [pool SEC](C:/Users/jvela/source/GABI/src/gabi/edgar.py:887)
- `history_refresh.run` crea carpeta por fecha/hora, hace `conn.backup(gabi_before.db)` y copia los CSV; `historical_backfill.run` vuelve a respaldar base por corrida; `sec_history.run_bulk` crea `before_validation.db` si aún no existe. [history_refresh.py](C:/Users/jvela/source/GABI/src/gabi/history_refresh.py:109), [historical_backfill.py](C:/Users/jvela/source/GABI/src/gabi/historical_backfill.py:73), [sec_history.py](C:/Users/jvela/source/GABI/src/gabi/sec_history.py:185)
- Nuevas auditorías crean SQLite snapshot completo, retenido y validado por hash. Rotación copia su snapshot a `rotation_experiment_work.db`. [full_universe_audit.py](C:/Users/jvela/source/GABI/src/gabi/full_universe_audit.py:42), [overfitting_audit.py](C:/Users/jvela/source/GABI/src/gabi/overfitting_audit.py:106), [rotation_experiment.py](C:/Users/jvela/source/GABI/src/gabi/rotation_experiment.py:83)
- Algunas descargas se escriben primero como `.part`, y luego se renombran; las fuentes son archivadas con SHA256 en SQLite. SEC descarga con streaming de 1 MB e importa `num.txt` en bloques de 200.000 filas. [sec_history.download](C:/Users/jvela/source/GABI/src/gabi/sec_history.py:59), [importación](C:/Users/jvela/source/GABI/src/gabi/sec_history.py:104)
- `periodic_tasks --run` puede iniciar una tarea más pesada una sola vez: `smallmid_test.final_run` importa caché Tiingo, recalcula checks, acuerdo Kaggle, rankings históricos y análisis. Por tanto no se puede dimensionar toda ejecución diaria suponiendo exclusivamente mantenimiento corto. [periodic_tasks.smallmid_step](C:/Users/jvela/source/GABI/src/gabi/periodic_tasks.py:120), [smallmid_test.final_run](C:/Users/jvela/source/GABI/src/gabi/smallmid_test.py:597)

### Inferences

- Hace falta un disco **persistente y escribible** montado donde apunta `config.DATA_DIR`, compartido por UI y jobs. Un runner efímero separado sin acceso a la SQLite no actualiza automáticamente la instancia servida.
- Una VM Linux puede mantener Streamlit en servicio y ejecutar CLI mediante cron/systemd. El script de Windows debe sustituirse; zona horaria, solapamiento de jobs y reinicio tras fallo deben configurarse. No se ha implementado despliegue ni un scheduler Linux.
- WAL ayuda a coexistir lectores y escritor, pero no elimina la serialización entre escritores ni la carga RAM/CPU. Para una instancia personal, una sola VM es una arquitectura coherente; varios contenedores con copias independientes de `data` no conservan automáticamente el mismo estado.
- Además del inventario retenido hay que reservar espacio para WAL, `.part`, importaciones y snapshots futuros. El backup SQLite usado por `history_refresh` incluye páginas WAL comprometidas; una transferencia de un `.db` activo mediante copia de archivo normal no garantiza lo mismo.

### Gaps

- No se ejecutaron jobs, descargas, análisis ni backtests. No están medidos duración, pico RAM, pico WAL, pico disco de cada job ni carga simultánea real.
- No se verificó si el programador Windows está instalado ni ejecución automática actual, y no se investigaron fuentes externas del proveedor de datos: sus cuotas no aumentan al cambiar de nube.

## ¿Qué sabemos de RAM, Linux ARM y antecedentes de despliegue?

### Takeaway

No existe en esta revisión un mínimo de RAM medido; disco de 83,2 GiB no equivale a necesitar 83,2 GiB de RAM. Linux ARM parece técnicamente plausible porque el lock incluye wheels para las dependencias compiladas, pero la combinación completa UI + jobs debe probarse antes de dar por suficiente una VM gratuita. [storage.get_prices_multi](C:/Users/jvela/source/GABI/src/gabi/storage.py:147), [uv.lock](C:/Users/jvela/source/GABI/uv.lock), [CI](C:/Users/jvela/source/GABI/.github/workflows/ci.yml:11)

### Cited Findings

- Python requerido >=3.12. Dependencias directas: Streamlit, yfinance, pandas, numpy, Plotly, lxml, requests, quantstats, PyPortfolioOpt, backtesting, exchange_calendars. CI está preparado para Ubuntu, `uv sync --locked --all-groups`, imports, compilación UI y tests; la configuración CI por sí sola no acredita un despliegue probado en ARM. [pyproject.toml](C:/Users/jvela/source/GABI/pyproject.toml:5), [ci.yml](C:/Users/jvela/source/GABI/.github/workflows/ci.yml:11)
- Inspección local del lock: hay wheels manylinux aarch64 CPython 3.12/3.13 o ABI3 para numpy 2.5.3, pandas 3.0.6, scipy 1.18.1, cvxpy 1.9.2, lxml 6.1.3, pyarrow 25.0.1, osqp 1.1.3, clarabel 0.11.1, curl-cffi 0.16.3, scs 3.3.1, matplotlib 3.11.2, contourpy 1.4.0 y pillow 12.3.0. Algunos requieren manylinux con glibc 2.28 o superior, por lo que conviene una distribución Linux reciente. Es inspección del lock, **no instalación ni test ARM**. [uv.lock](C:/Users/jvela/source/GABI/uv.lock)
- El screener carga precios del conjunto solicitado en un único DataFrame y después construye grupos por símbolo; consulta todo su histórico en `prices`, sin recorte de fechas en esa función. Importaciones y varias sesiones pueden multiplicar memoria. [screener.py](C:/Users/jvela/source/GABI/src/gabi/screener.py:59), [storage.py](C:/Users/jvela/source/GABI/src/gabi/storage.py:147)
- Importación Kaggle lee bloques de 2.000.000 filas y retiene subconjuntos en una lista antes de concatenar; además calcula SHA256 del ZIP con `read_bytes()`. El ZIP local mide 485.974.042 bytes. Esto apunta a un pico mayor que una pantalla ligera, sin permitir calcular RAM máxima con precisión. [smallmid_test.py](C:/Users/jvela/source/GABI/src/gabi/smallmid_test.py:435), [Inventario ZIP](C:/Users/jvela/source/GABI/research_notes/Viabilidad%20gratuita%20de%20GABI/medicion_data.json)
- El proyecto presenta tareas periódicas como opcionales/locales y menciona cron como mejora futura. [README tareas](C:/Users/jvela/source/GABI/README.md:1451), [README futuro](C:/Users/jvela/source/GABI/README.md:1717)

### Inferences

- Una VM con 12 GB RAM es una **candidata evaluable**, no una suficiencia demostrada. No hay base para asegurar 1 GB, 2 GB, 4 GB ni 12 GB como mínimo universal; especialmente para imports, research y concurrencia.
- Cambiar a ARM no implica reescribir código de negocio según las rutas y dependencias inspeccionadas. Sí requiere instalación limpia, probar importaciones y jobs, y revisar cualquier dependencia que intente compilarse.
- Un plan cloud debe indicar si cubre uso cotidiano y jobs de actualización solamente o también nuevas auditorías/importaciones grandes. El usuario pregunta por la aplicación completa y crecimiento de datos, así que asumir sólo una portada vacía sería una comparación inválida.

### Gaps

- `Get-Process python,pythonw,streamlit` no encontró un proceso activo accesible durante la revisión. No se inició la app para medir memoria, no se ejecutaron backtests ni consultas grandes y no se identificó instrumentación `psutil`, `tracemalloc`, `memory_usage`, `@st.cache_data` o `@st.cache_resource` en src/app/tests. El consumo RAM de reposo y máximo real siguen **sin medir**.
- No se encontró una propuesta de despliegue en nube en la búsqueda de docs/README ni en títulos de commits de las últimas revisiones consultadas con palabras nube/cloud/deploy/hosting/Oracle. No se consultaron conversaciones fuera del repo ni issues remotos; la conversación reciente que cita el usuario puede estar ahí.
- No se comprobó ejecución real ARM, ni disponibilidad de red/cupos de las fuentes desde IP cloud. No hay benchmark que garantice que UI y jobs intensivos simultáneos caben en el límite gratuito de RAM/CPU.
