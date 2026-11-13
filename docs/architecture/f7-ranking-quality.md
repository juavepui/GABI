# Ranking histórico y calidad de datos sin storage (F7.22, #132)

Primera entrega de #132. El ranking point-in-time y la observabilidad de datos dejan
la fachada `storage`, y los alias pequeños se sustituyen por el dominio:

| Módulo | Antes | Ahora |
| --- | --- | --- |
| `screener_asof` (caché por ticker de emisores sin alias) | `storage.get_price_as_of`, `has_verified_price_as_of`, `get_split_factor_since`, `get_prices` | `application/market/cached_data` sobre `identity.cache_reads()` (`SqliteCacheReads` resuelto por operación) |
| `screener_asof` (capa acreditada) | `historical_pit.covers` / `as_traded_close` | `identity.accredited_history()` y `application/research/historical_pit.as_traded_close` |
| `screener_asof` (persistencia, asignación de capital, expectativas) | alias `quality_persistence`, `capital_allocation`, `valuation_expectations` | `application/market/quality.quality_as_of`, `domain/portfolio/capital_allocation`, `domain/market/valuation_expectations` |
| `data_quality` (cobertura, fundamentales, errores) | `storage.get_*` | `cached_data` sobre `SqliteCacheReads(config.DB_PATH)` |
| `data_quality.local_cik_status` | `storage.get_connection` (leía toda `cik_resolutions`) | `SqliteCikResolutions.cached_many`, en lotes de 1.000 símbolos y en solo lectura |
| `data_quality.compute_data_fingerprint` | SQL en la fachada sobre `storage.get_connection` | `infrastructure/storage/data_fingerprint.py`: la misma huella v2 en una transacción de solo lectura |
| `multifactor_backtest`, `portfolio_backtest` | alias `rotation_policy`, `broker_costs` | `domain/portfolio/rotation`, `domain/portfolio/broker_costs` |

`screener_asof` conserva `entity_master.get_sector_asof`, porque `smallmid_test`, que
reproduce un resultado publicado, lo parchea para inyectar sectores SIC. También
conserva `identity`, `edgar`, `technicals`, `risk`, `scoring` y `universe`, que leen
por nombre `overfitting_audit` (motor congelado) y los motores que parchean
`config.DB_PATH` por variante. Los lectores resuelven la ruta en cada llamada, así
que esos parches siguen funcionando.

## Alias

- **Retirados** (sin importadores de producción): `capital_allocation`,
  `valuation_expectations`, `quality_persistence` y `broker_costs`. Las pruebas importan
  el dominio.
- **Se conserva** `rotation_policy`. `rotation_experiment` registra en su protocolo el
  `code_sha256` de `rotation_policy.py` por nombre de archivo, y ese protocolo está
  publicado en `docs/rotation-experiment/`. Ya no tiene otros importadores. Pasa a la
  lista de #135.

Inventario: −10 dependencias; quedan 70 módulos planos.

## Efectos

- Las lecturas del ranking y de la calidad de datos ya no crean la base ni ponen WAL
  al consultar. Una base ausente equivale a una caché vacía.
- La huella de una base ausente es la de tablas vacías, igual que antes, pero ya no
  crea el archivo.
- Como en F7.14–F7.21, editar `screener_asof.py`, `multifactor_backtest.py` e
  `identity.py` invalida la caché local de `overfitting_audit`, que los lee por nombre.
  Los resultados publicados no cambian.

## Validación y medida

`fixtures/ranking_quality_migration.json` captura `screener_asof`, `data_quality` y
los cinco alias de `c324aabadf3c7b517129f5cd55ffff880921d865`.
`test_ranking_quality_migration.py` ejecuta el código capturado dentro del paquete y lo
compara con el nuevo:

- **Ranking:** tres fechas × identidad estricta o no × dos juegos de pesos. Emisores
  con alias y por ticker, un split posterior y otro anterior a la fecha, una caché sin
  `adj_close`, un símbolo sin datos, ingresos negativos, sectores y benchmark.
  Además se comparan la tabla completa, `universe_info`, las métricas clásicas,
  los diagnósticos y las series de precios por símbolo.
- **Capa acreditada:** con y sin periodo 2010–2015 activo, con una serie Yahoo y
  un split posterior.
- **Calidad de datos:** con reloj fijo. Cubre el resumen del universo, la procedencia,
  los CIK locales (tabla y CSV, incluido `BRK.B`), los errores en ventanas de 1 h y
  7 días, la cobertura de bloques y la calidad del ranking.
- **Huella:** cuatro selecciones de símbolos con CSV del universo, sin escribir en la
  base, y una base ausente que no se crea.
- **Alias:** los capturados eran exactamente el dominio.

Doce mutaciones deliberadas (precio verificado, split, cobertura acreditada, cierre
negociado, persistencia, símbolo de la caché, columnas ignoradas y JSON de la huella,
filtro de símbolos, lotes de CIK, ventana de errores y fundamentales) hacen fallar
pruebas.

Medida: `.venv/Scripts/python.exe scripts/measure_f7_ranking_quality.py`.
Windows/Python 3.13, 120 emisores (la mitad con alias) y 400 sesiones, tablas
idénticas. Mediana de 3 en dos ejecuciones:

| Flujo | Anterior (s) | Nuevo (s) |
| --- | --- | --- |
| Ranking a fecha | 10,33 / 11,23 | 10,39 / 9,86 |
| Huella de datos | 0,99 / 0,88 | 0,89 / 0,87 |

Sin cambio apreciable. El coste del ranking está en el cálculo por símbolo, no en
las lecturas que se han movido.

Las entradas explícitas de `multifactor_backtest` y `portfolio_backtest` llegan en la
segunda entrega: [F7.24](f7-backtest-inputs.md).
